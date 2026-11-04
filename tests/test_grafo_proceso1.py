"""Pruebas del grafo determinista del proceso 1, sin modelo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from langgraph.types import Command

from app import db
from app.grafo_proceso1 import construir_grafo


@pytest.fixture()
def grafo(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "RUTA_PROCESO1", tmp_path / "proceso1.db")
    db.reiniciar_proceso1()
    return construir_grafo()


def solicitud(**cambios):
    datos = {
        "solicitante": "Marco Ruiz Delgado",
        "telefono": "987654321",
        "placa": "A1B-234",
        "tipo_servicio": "preventivo_10000",
        "fecha_solicitada": "2026-10-21",
        "descripcion": "",
    }
    datos.update(cambios)
    return datos


def invocar(grafo, hilo, datos, respuestas=None):
    respuestas = list(respuestas or [])
    config = {"configurable": {"thread_id": hilo}}
    estado = grafo.invoke({"solicitud": datos}, config=config)
    pausas = []
    while estado.get("__interrupt__"):
        pausas.append(estado["__interrupt__"][0].value)
        if not respuestas:
            raise AssertionError(f"El grafo se pauso sin una respuesta preparada: {pausas[-1]}")
        estado = grafo.invoke(Command(resume=respuestas.pop(0)), config=config)
    return estado, pausas


def test_flujo_feliz_registra_cita_y_ejecuta_ramas_paralelas(grafo):
    estado, pausas = invocar(grafo, "feliz", solicitud())

    assert pausas == []
    assert estado["resultado"]["ok"] is True
    assert estado["resultado"]["id_cita"] == "CITA-0002"
    assert estado["consulta_cupo"]["ok"] is True
    assert estado["consulta_kit"]["ok"] is True
    assert estado["ruta_g4"] == "g4b_continuar"
    assert estado["ruta_g6b"] == "s12r_registrar"
    with db.abrir_proceso1() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"] == 2


def test_cita_existente_no_duplica(grafo):
    estado, pausas = invocar(
        grafo,
        "existente",
        solicitud(placa="T4M-891", fecha_solicitada="2026-10-20"),
    )

    assert pausas == []
    assert estado["resultado"]["estado"] == "ya_existe"
    assert estado["resultado"]["cita"]["id_cita"] == "CITA-0001"
    with db.abrir_proceso1() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"] == 1


def test_datos_invalidos_pausan_en_h1r(grafo):
    estado, pausas = invocar(
        grafo,
        "invalidos",
        solicitud(
            placa="ABC123",
            tipo_servicio="preventivo_15000",
            fecha_solicitada="2026-10-01",
            telefono="12345",
        ),
        [{"corregido": True}],
    )

    assert [pausa["nodo"] for pausa in pausas] == ["H1r"]
    assert len(pausas[0]["errores"]) == 4
    assert estado["resultado"]["estado"] == "devuelta_para_correccion"
    with db.abrir_proceso1() as conn:
        fila = conn.execute("SELECT motivo FROM cola_excepciones").fetchone()
        assert fila["motivo"] == "OTRO"
        assert conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"] == 1


def test_posible_correctivo_pausa_en_h2d_y_deriva(grafo):
    estado, pausas = invocar(
        grafo,
        "correctivo",
        solicitud(placa="E5F-678", fecha_solicitada="2026-10-23", descripcion="suena raro al frenar"),
        [{"decision": "correctivo"}],
    )

    assert [pausa["nodo"] for pausa in pausas] == ["H2d"]
    assert estado["resultado"]["estado"] == "derivado_correctivo"
    assert estado["excepcion_id"] == "EXC-0001"
    with db.abrir_proceso1() as conn:
        assert conn.execute("SELECT motivo FROM cola_excepciones").fetchone()["motivo"] == "POSIBLE_CORRECTIVO"
        assert conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"] == 1


def test_h2d_puede_devolver_el_caso_a_preventivo(grafo):
    estado, pausas = invocar(
        grafo,
        "preventivo",
        solicitud(placa="E5F-678", fecha_solicitada="2026-10-23", descripcion="suena raro al frenar"),
        [{"decision": "preventivo"}],
    )

    assert [pausa["nodo"] for pausa in pausas] == ["H2d"]
    assert estado["ruta_g3c"] == "g3b_continuar"
    assert estado["resultado"]["id_cita"] == "CITA-0002"


def test_sin_kit_pausa_en_h3k_y_cierra_gestionado(grafo):
    estado, pausas = invocar(
        grafo,
        "sin-kit",
        solicitud(placa="C3D-456", tipo_servicio="preventivo_5000"),
        [{"decision": "gestionado"}],
    )

    assert [pausa["nodo"] for pausa in pausas] == ["H3k"]
    assert estado["resultado"]["estado"] == "kit_gestionado"
    assert estado["excepcion_id"] == "EXC-0001"
    with db.abrir_proceso1() as conn:
        assert conn.execute("SELECT motivo FROM cola_excepciones").fetchone()["motivo"] == "SIN_KIT"
        assert conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"] == 1


def test_duracion_larga_pausa_en_h4a_y_no_registra(grafo):
    estado, pausas = invocar(
        grafo,
        "duracion-larga",
        solicitud(placa="D4E-567", tipo_servicio="preventivo_20000"),
        [{"aprobado": True}],
    )

    assert [pausa["nodo"] for pausa in pausas] == ["H4a"]
    assert estado["aprobacion"] == "aprobado"
    assert estado["resultado"]["codigo"] == "REQUIERE_APROBACION"
    assert estado.get("cita") is None
    with db.abrir_proceso1() as conn:
        assert conn.execute("SELECT motivo FROM cola_excepciones").fetchone()["motivo"] == "REQUIERE_APROBACION"
        assert conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"] == 1


def test_h4a_rechazado_cierra_sin_registrar(grafo):
    estado, pausas = invocar(
        grafo,
        "rechazo",
        solicitud(placa="D4E-567", tipo_servicio="preventivo_20000"),
        [{"aprobado": False}],
    )

    assert [pausa["nodo"] for pausa in pausas] == ["H4a"]
    assert estado["resultado"]["estado"] == "rechazada_por_jefe"
    with db.abrir_proceso1() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"] == 1


def test_sin_cupo_ofrece_alternativas_y_reintenta(grafo):
    estado, pausas = invocar(
        grafo,
        "sin-cupo",
        solicitud(placa="B2C-345", fecha_solicitada="2026-10-22"),
        [{"fecha": "2026-10-23"}],
    )

    assert [pausa["nodo"] for pausa in pausas] == ["IC_msg"]
    assert pausas[0]["alternativas"] == [
        {"fecha": "2026-10-23", "hora": "08:00"},
        {"fecha": "2026-10-26", "hora": "08:00"},
        {"fecha": "2026-10-27", "hora": "08:00"},
    ]
    assert estado["fecha_elegida"] == "2026-10-23"
    assert estado["resultado"]["id_cita"] == "CITA-0002"


def test_grafo_expone_nodos_bpmn_y_ramas_paralelas(grafo):
    nodos = set(grafo.get_graph().nodes)

    assert {
        "s1v_validar",
        "g1_contrato",
        "s2c_registrar_cola",
        "h1r_corregir",
        "s3n_normalizar",
        "s2b_consultar_clave",
        "g2_clave_existe",
        "s4d_devolver",
        "s5c_clasificar",
        "g3_preventivo",
        "s_rev_encolar",
        "h2d_resolver",
        "g3c_resolucion",
        "s6d_notificar",
        "g3b_continuar",
        "and1",
        "s7c_consultar_cupo",
        "s8k_verificar_kit",
        "and2",
        "g4_clasificar",
        "s_kit_encolar",
        "h3k_gestionar",
        "s9q_alternativas",
        "s9a_proponer",
        "g5_eleccion",
        "ic_msg",
        "ic_t24",
        "s10d_desistida",
        "g4b_continuar",
        "g6_duracion",
        "s_apr_encolar",
        "h4a_aprobar",
        "g6b_decision",
        "s12r_registrar",
        "s14c_confirmar",
        "s_cls",
        "s13f_cola_fallidos",
        "h5r_reprogramar",
        "be_cupo",
        "be_kit",
        "be_alt",
        "be_err",
        "bt_kit",
        "end_1",
        "end_2",
        "end_3",
        "end_4",
        "end_5",
        "end_6",
        "end_7",
    } <= nodos
