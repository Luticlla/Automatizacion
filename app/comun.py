"""Errores, testigos, bitacora, cola de excepciones y reintentos comunes."""
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

MINUTOS_VIGENCIA_TESTIGO = 30
INTENTOS_BLOQUEO = 3
ESPERA_BLOQUEO = 0.2


def ahora_texto():
    """Marca de tiempo local en formato comparable como texto."""
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def error(codigo, mensaje, que_hacer, clase="datos", **extra):
    """Diccionario estandar de error."""
    respuesta = {"ok": False, "codigo": codigo, "mensaje": mensaje, "que_hacer": que_hacer, "clase": clase}
    respuesta.update(extra)
    return respuesta


@contextmanager
def transaccion(conn):
    """Ejecuta un bloque de escritura como una sola transaccion."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def emitir_testigo(conn, accion, clave):
    """Emite un testigo de un solo uso para una accion y lo guarda en testigos."""
    token = "T-" + secrets.token_hex(4).upper()
    expira = datetime.now() + timedelta(minutes=MINUTOS_VIGENCIA_TESTIGO)
    conn.execute(
        "INSERT INTO testigos (token, accion, clave, usado, creado_en, expira_en) VALUES (?, ?, ?, 0, ?, ?)",
        (token, accion, clave, ahora_texto(), expira.isoformat(sep=" ", timespec="seconds")),
    )
    return token


def consumir_testigo(conn, token, accion):
    """Valida y marca como usado un testigo; devuelve la fila o None si no sirve."""
    fila = conn.execute(
        "SELECT * FROM testigos WHERE token = ? AND accion = ?", (token, accion)
    ).fetchone()
    if fila is None or fila["usado"] or fila["expira_en"] < ahora_texto():
        return None
    conn.execute("UPDATE testigos SET usado = 1 WHERE token = ?", (token,))
    return fila


def registrar_bitacora(conn, clave, herramienta, codigo):
    """Anota una linea de bitacora con la herramienta y su codigo de resultado."""
    conn.execute(
        "INSERT INTO bitacora (clave, herramienta, codigo, ts) VALUES (?, ?, ?, ?)",
        (clave or "", herramienta, codigo, ahora_texto()),
    )


def _buscar_solicitud(conn, clave):
    """Datos de la solicitud validada, si esta base tiene esa tabla."""
    tabla = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'solicitudes_validadas'"
    ).fetchone()
    if tabla is None:
        return None
    fila = conn.execute(
        "SELECT datos_json FROM solicitudes_validadas WHERE clave = ?", (clave,)
    ).fetchone()
    if fila is None:
        return None
    return json.loads(fila["datos_json"])


def derivar(conn, proceso, motivo, consulta_original, clave="", datos_extra=None):
    """Encola una excepcion para un asesor y devuelve la confirmacion."""
    pasos = []
    if clave:
        pasos = [
            {"herramienta": paso["herramienta"], "codigo": paso["codigo"], "ts": paso["ts"]}
            for paso in conn.execute(
                "SELECT herramienta, codigo, ts FROM bitacora WHERE clave = ? ORDER BY id", (clave,)
            )
        ]
    datos = {"pasos": pasos}
    solicitud = _buscar_solicitud(conn, clave) if clave else None
    if solicitud is not None:
        datos["solicitud"] = solicitud
    if datos_extra:
        datos.update(datos_extra)
    ultima = conn.execute("SELECT id FROM cola_excepciones ORDER BY id DESC LIMIT 1").fetchone()
    numero = 1 if ultima is None else int(ultima["id"].split("-")[1]) + 1
    id_excepcion = f"EXC-{numero:04d}"
    conn.execute(
        "INSERT INTO cola_excepciones (id, fecha_hora, proceso, motivo, consulta_original, datos_json, estado)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            id_excepcion,
            ahora_texto(),
            proceso,
            motivo,
            consulta_original,
            json.dumps(datos, ensure_ascii=False),
            "pendiente",
        ),
    )
    return {"ok": True, "id_excepcion": id_excepcion, "mensaje": "Un asesor revisará tu caso."}


def con_reintento(funcion):
    """Reintenta si SQLite esta bloqueada; si sigue, devuelve error transitorio."""
    for intento in range(INTENTOS_BLOQUEO):
        try:
            return funcion()
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc):
                raise
            if intento == INTENTOS_BLOQUEO - 1:
                return error(
                    "BASE_OCUPADA",
                    "La base de datos esta ocupada.",
                    "Reintenta en unos segundos.",
                    clase="transitorio",
                )
            time.sleep(ESPERA_BLOQUEO)
