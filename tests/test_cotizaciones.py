"""Pruebas de la logica del proceso 2 sobre una base temporal reiniciada."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import db
from app.mcp_cotizaciones import logica


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "RUTA_PROCESO2", tmp_path / "proceso2.db")
    db.reiniciar_proceso2()
    conexion = db.conectar(db.RUTA_PROCESO2)
    yield conexion
    conexion.close()


def test_consultar_tarifario_una_coincidencia(conn):
    respuesta = logica.consultar_tarifario(conn, "frena mal y hace ruido al frenar")
    assert respuesta["ok"] is True
    assert len(respuesta["coincidencias"]) == 1
    coincidencia = respuesta["coincidencias"][0]
    assert coincidencia["codigo"] == "FRE-01"
    assert coincidencia["precio_total_soles"] == 270
    assert "FRE-01" in respuesta["que_hacer"] or "ese codigo" in respuesta["que_hacer"]


def test_varias_coincidencias_y_monto_alto(conn):
    busqueda = logica.consultar_tarifario(conn, "cambio de embrague y cambio de correa de distribucion")
    codigos = [coincidencia["codigo"] for coincidencia in busqueda["coincidencias"]]
    assert set(codigos) == {"EMB-01", "DIS-01"}

    armado = logica.armar_cotizacion(conn, ["EMB-01", "DIS-01"], "Honda Civic 2020")
    assert armado["ok"] is True
    assert armado["total"] == 2500

    politica = logica.validar_politica_comercial(conn, armado["id_cotizacion"])
    assert politica["ok"] is False
    assert politica["codigo"] == "MONTO_REQUIERE_APROBACION"
    assert "testigo" not in politica
    estado = conn.execute(
        "SELECT estado FROM cotizaciones WHERE id_cotizacion = ?", (armado["id_cotizacion"],)
    ).fetchone()["estado"]
    assert estado == "pendiente_aprobacion"


def test_servicio_no_encontrado(conn):
    respuesta = logica.consultar_tarifario(conn, "aire acondicionado nuevo")
    assert respuesta["ok"] is False
    assert respuesta["codigo"] == "SERVICIO_NO_ENCONTRADO"


def test_descuento_no_permitido(conn):
    armado = logica.armar_cotizacion(conn, ["FRE-01"], "Toyota Corolla 2019")
    politica = logica.validar_politica_comercial(conn, armado["id_cotizacion"], descuento_solicitado_pct=10)
    assert politica["ok"] is True
    assert politica["aviso"]["codigo"] == "DESCUENTO_NO_PERMITIDO"
    assert politica["total"] == 270
    assert politica["testigo"].startswith("T-")
    assert politica["vigencia_dias"] == 7


def test_codigo_inexistente_no_crea_cotizacion(conn):
    respuesta = logica.armar_cotizacion(conn, ["FRE-01", "XXX-99"], "Toyota Corolla 2019")
    assert respuesta["ok"] is False
    assert respuesta["codigo"] == "SERVICIO_NO_ENCONTRADO"
    total = conn.execute("SELECT COUNT(*) AS n FROM cotizaciones").fetchone()["n"]
    assert total == 0


def test_testigo_reemplazado_y_usado_dos_veces(conn):
    armado = logica.armar_cotizacion(conn, ["FRE-01"], "Toyota Corolla 2019")
    primero = logica.validar_politica_comercial(conn, armado["id_cotizacion"])
    segundo = logica.validar_politica_comercial(conn, armado["id_cotizacion"])

    viejo = logica.programar_servicio(conn, primero["testigo"], "aceptar")
    assert viejo["ok"] is False
    assert viejo["codigo"] == "TESTIGO_INVALIDO"

    aceptado = logica.programar_servicio(conn, segundo["testigo"], "aceptar")
    assert aceptado["ok"] is True

    repetido = logica.programar_servicio(conn, segundo["testigo"], "aceptar")
    assert repetido["codigo"] == "TESTIGO_INVALIDO"


def test_aceptar_crea_orden_y_es_idempotente(conn):
    armado = logica.armar_cotizacion(conn, ["FRE-01"], "Toyota Corolla 2019")
    assert armado["id_cotizacion"] == "COT-0001"

    testigo = logica.validar_politica_comercial(conn, armado["id_cotizacion"])["testigo"]
    primera = logica.programar_servicio(conn, testigo, "aceptar")
    assert primera["ok"] is True
    assert primera["id_ot"] == "OT-0001"
    estado = conn.execute(
        "SELECT estado FROM cotizaciones WHERE id_cotizacion = ?", (armado["id_cotizacion"],)
    ).fetchone()["estado"]
    assert estado == "aceptada"

    testigo2 = logica.validar_politica_comercial(conn, armado["id_cotizacion"])["testigo"]
    segunda = logica.programar_servicio(conn, testigo2, "aceptar")
    assert segunda["ok"] is True
    assert segunda["id_ot"] == "OT-0001"
    total = conn.execute("SELECT COUNT(*) AS n FROM ordenes_trabajo").fetchone()["n"]
    assert total == 1


def test_rechazar_no_crea_orden(conn):
    armado = logica.armar_cotizacion(conn, ["FRE-01"], "Toyota Corolla 2019")
    testigo = logica.validar_politica_comercial(conn, armado["id_cotizacion"])["testigo"]
    respuesta = logica.programar_servicio(conn, testigo, "rechazar")
    assert respuesta["ok"] is True
    estado = conn.execute(
        "SELECT estado FROM cotizaciones WHERE id_cotizacion = ?", (armado["id_cotizacion"],)
    ).fetchone()["estado"]
    assert estado == "rechazada"
    total = conn.execute("SELECT COUNT(*) AS n FROM ordenes_trabajo").fetchone()["n"]
    assert total == 0


def test_decision_invalida(conn):
    respuesta = logica.programar_servicio(conn, "T-00000000", "tal vez")
    assert respuesta["ok"] is False
    assert "aceptar" in respuesta["que_hacer"]
    assert "rechazar" in respuesta["que_hacer"]


def test_errores_traen_las_cuatro_claves(conn):
    respuestas = [
        logica.consultar_tarifario(conn, "aire acondicionado nuevo"),
        logica.armar_cotizacion(conn, ["NO-EXISTE"], "Toyota Corolla 2019"),
        logica.validar_politica_comercial(conn, "COT-9999"),
        logica.programar_servicio(conn, "T-00000000"),
        logica.programar_servicio(conn, "T-00000000", "tal vez"),
    ]
    for respuesta in respuestas:
        assert respuesta["ok"] is False
        assert {"codigo", "mensaje", "que_hacer", "clase"} <= set(respuesta)


def test_derivar_incluye_cotizacion_y_pasos(conn):
    armado = logica.armar_cotizacion(conn, ["FRE-01"], "Toyota Corolla 2019")
    respuesta = logica.derivar_a_humano(
        conn, "MONTO_REQUIERE_APROBACION", "el total no cuadra", armado["id_cotizacion"]
    )
    assert respuesta["ok"] is True
    assert respuesta["id_excepcion"] == "EXC-0001"

    fila = conn.execute("SELECT * FROM cola_excepciones").fetchone()
    assert fila["proceso"] == "cotizacion"
    assert fila["motivo"] == "MONTO_REQUIERE_APROBACION"
    assert fila["consulta_original"] == "el total no cuadra"
    assert fila["estado"] == "pendiente"
    datos = json.loads(fila["datos_json"])
    assert datos["cotizacion"]["id_cotizacion"] == armado["id_cotizacion"]
    assert len(datos["pasos"]) >= 1

    logica.derivar_a_humano(conn, "motivo raro", "consulta", "")
    fila = conn.execute("SELECT motivo FROM cola_excepciones ORDER BY id DESC LIMIT 1").fetchone()
    assert fila["motivo"] == "OTRO"
