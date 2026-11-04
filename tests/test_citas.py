"""Pruebas de la logica del proceso 1 sobre una base temporal reiniciada."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import db
from app.mcp_citas import logica


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "RUTA_PROCESO1", tmp_path / "proceso1.db")
    db.reiniciar_proceso1()
    conexion = db.conectar(db.RUTA_PROCESO1)
    yield conexion
    conexion.close()


def solicitud_valida(**cambios):
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


def test_clave_idempotencia():
    assert (
        logica.calcular_clave("T4M-891", "2026-09-22", "preventivo_10000")
        == "1b114e68d6a3241784560e39cf0868d9"
    )


def test_errores_traen_codigo_mensaje_que_hacer_clase(conn):
    contrato = logica.validar_solicitud(conn, **solicitud_valida(placa="ABC123", telefono="12345"))
    assert contrato["ok"] is False
    assert contrato["clase"] == "datos"
    for item in contrato["errores"]:
        assert {"codigo", "mensaje", "que_hacer"} <= set(item)

    desconocida = logica.consultar_disponibilidad(conn, "clave-inexistente")
    assert desconocida["ok"] is False
    assert {"codigo", "mensaje", "que_hacer", "clase"} <= set(desconocida)

    invalido = logica.confirmar_cita(conn, "T-00000000")
    assert invalido["ok"] is False
    assert {"codigo", "mensaje", "que_hacer", "clase"} <= set(invalido)
    assert invalido["codigo"] == "TESTIGO_INVALIDO"


def test_contrato_devuelve_todos_los_errores(conn):
    respuesta = logica.validar_solicitud(
        conn,
        solicitante="Juan Perez",
        telefono="12345",
        placa="ABC123",
        tipo_servicio="preventivo_15000",
        fecha_solicitada="2026-10-01",
    )
    codigos = sorted(item["codigo"] for item in respuesta["errores"])
    assert codigos == [
        "FECHA_INVALIDA",
        "PLACA_INVALIDA",
        "TELEFONO_INVALIDO",
        "TIPO_INVALIDO",
    ]

    vacios = logica.validar_solicitud(conn)
    assert len(vacios["errores"]) == 5
    assert all(item["codigo"] == "CAMPO_FALTANTE" for item in vacios["errores"])


def test_orden_kit_antes_que_cupo(conn):
    validacion = logica.validar_solicitud(
        conn, **solicitud_valida(placa="C3D-456", tipo_servicio="preventivo_5000", fecha_solicitada="2026-10-22")
    )
    assert validacion["ok"] is True
    assert validacion["estado"] == "valida"
    respuesta = logica.consultar_disponibilidad(conn, validacion["clave"])
    assert respuesta["codigo"] == "SIN_KIT"


def test_alternativas_sin_cupo(conn):
    validacion = logica.validar_solicitud(conn, **solicitud_valida(placa="B2C-345", fecha_solicitada="2026-10-22"))
    respuesta = logica.consultar_disponibilidad(conn, validacion["clave"])
    assert respuesta["codigo"] == "SIN_CUPO"
    assert respuesta["alternativas"] == [
        {"fecha": "2026-10-23", "hora": "08:00"},
        {"fecha": "2026-10-26", "hora": "08:00"},
        {"fecha": "2026-10-27", "hora": "08:00"},
    ]


def test_duracion_requiere_aprobacion(conn):
    validacion = logica.validar_solicitud(conn, **solicitud_valida(tipo_servicio="preventivo_20000"))
    respuesta = logica.consultar_disponibilidad(conn, validacion["clave"])
    assert respuesta["codigo"] == "REQUIERE_APROBACION"


def test_solicitud_repetida_ya_existe(conn):
    primera = logica.validar_solicitud(conn, **solicitud_valida(placa="T4M-891", fecha_solicitada="2026-10-20"))
    segunda = logica.validar_solicitud(conn, **solicitud_valida(placa="T4M-891", fecha_solicitada="2026-10-20"))
    assert primera["estado"] == "ya_existe"
    assert primera["cita"]["id_cita"] == "CITA-0001"
    assert segunda["estado"] == "ya_existe"
    assert segunda["cita"]["id_cita"] == "CITA-0001"
    total = conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"]
    assert total == 1


def test_testigo_reusado(conn):
    validacion = logica.validar_solicitud(conn, **solicitud_valida())
    preparacion = logica.preparar_cita(conn, validacion["clave"])
    primera = logica.confirmar_cita(conn, preparacion["testigo"])
    assert primera["ok"] is True
    assert primera["id_cita"] == "CITA-0002"

    segunda = logica.confirmar_cita(conn, preparacion["testigo"])
    assert segunda["codigo"] == "TESTIGO_INVALIDO"
    total = conn.execute("SELECT COUNT(*) AS n FROM citas").fetchone()["n"]
    assert total == 2


def test_recorrido_feliz(conn):
    validacion = logica.validar_solicitud(conn, **solicitud_valida())
    assert validacion["estado"] == "valida"

    disponibilidad = logica.consultar_disponibilidad(conn, validacion["clave"])
    assert disponibilidad["ok"] is True
    assert disponibilidad["hora"] == "08:00"
    assert disponibilidad["bahia"] == "B1"
    assert disponibilidad["tecnico"] == "Carlos Vega"
    assert disponibilidad["kit"] == "KIT-10K"
    assert disponibilidad["duracion_horas"] == 2.0

    preparacion = logica.preparar_cita(conn, validacion["clave"])
    assert preparacion["ok"] is True
    assert preparacion["resumen"]["placa"] == "A1B-234"
    assert preparacion["testigo"].startswith("T-")

    confirmacion = logica.confirmar_cita(conn, preparacion["testigo"])
    assert confirmacion["ok"] is True
    assert confirmacion["id_cita"] == "CITA-0002"
    assert confirmacion["hora"] == "08:00"
    assert confirmacion["bahia"] == "B1"

    estado = conn.execute(
        "SELECT estado FROM agenda WHERE fecha = '2026-10-21' AND hora = '08:00' AND bahia = 'B1'"
    ).fetchone()["estado"]
    assert estado == "ocupado"
    stock = conn.execute(
        "SELECT stock FROM kits WHERE tipo_servicio = 'preventivo_10000'"
    ).fetchone()["stock"]
    assert stock == 3


def test_descripcion_con_falla(conn):
    validacion = logica.validar_solicitud(
        conn, **solicitud_valida(placa="E5F-678", descripcion="suena raro al frenar")
    )
    assert validacion["ok"] is True
    assert validacion["estado"] == "posible_falla"
    assert "POSIBLE_CORRECTIVO" in validacion["que_hacer"]


def test_derivar_guarda_cola(conn):
    validacion = logica.validar_solicitud(conn, **solicitud_valida())
    respuesta = logica.derivar_a_humano(conn, "POSIBLE_CORRECTIVO", "el auto suena raro", validacion["clave"])
    assert respuesta["ok"] is True
    assert respuesta["id_excepcion"] == "EXC-0001"

    fila = conn.execute("SELECT * FROM cola_excepciones").fetchone()
    assert fila["proceso"] == "citas"
    assert fila["motivo"] == "POSIBLE_CORRECTIVO"
    assert fila["consulta_original"] == "el auto suena raro"
    assert fila["estado"] == "pendiente"
    datos = json.loads(fila["datos_json"])
    assert datos["solicitud"]["placa"] == "A1B-234"
    assert len(datos["pasos"]) >= 1


def test_motivo_desconocido_se_guarda_como_otro(conn):
    logica.derivar_a_humano(conn, "cualquier cosa", "consulta del cliente")
    fila = conn.execute("SELECT motivo FROM cola_excepciones").fetchone()
    assert fila["motivo"] == "OTRO"
