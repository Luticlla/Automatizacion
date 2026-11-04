"""Logica pura del proceso 1: funciones que reciben una conexion y devuelven diccionarios."""
import hashlib
import json
import re
import unicodedata
from datetime import date

from app import comun, config

TIPOS_SERVICIO = ("preventivo_5000", "preventivo_10000", "preventivo_20000")
PALABRAS_DE_FALLA = (
    "ruido", "falla", "golpe", "fuga", "vibra", "humo",
    "no arranca", "se calienta", "frena mal", "suena raro",
)
MOTIVOS_DERIVACION = (
    "POSIBLE_CORRECTIVO", "SIN_KIT", "REQUIERE_APROBACION",
    "FUERA_DE_ALCANCE", "LIMITE_DE_ITERACIONES", "ERROR_DE_SISTEMA",
)

PATRON_TELEFONO = re.compile(r"^9[0-9]{8}$")
PATRON_PLACA = re.compile(r"^[A-Z][A-Z0-9]{2}-[0-9]{3}$")
PATRON_FECHA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def sin_tildes(texto):
    """Quita las tildes para comparar textos."""
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def calcular_clave(placa, fecha, tipo_servicio):
    """Clave de idempotencia: SHA-256 de placa_sin_guion|fecha|tipo, 32 hex."""
    crudo = f"{placa.replace('-', '')}|{fecha}|{tipo_servicio}"
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:32]


def _error_campo_faltante(campo):
    return comun.error("CAMPO_FALTANTE", f"Falta el campo {campo}.", "Pedir al cliente ese dato.")


def _tiene_palabra_de_falla(descripcion):
    texto = sin_tildes(descripcion.lower())
    return any(sin_tildes(palabra) in texto for palabra in PALABRAS_DE_FALLA)


def _solicitud(conn, clave):
    fila = conn.execute(
        "SELECT datos_json FROM solicitudes_validadas WHERE clave = ?", (clave,)
    ).fetchone()
    if fila is None:
        return None
    return json.loads(fila["datos_json"])


def _registrar(conn, clave, herramienta, resultado):
    with comun.transaccion(conn):
        comun.registrar_bitacora(conn, clave, herramienta, "OK" if resultado.get("ok") else resultado.get("codigo", "ERROR"))


def validar_solicitud(conn, solicitante="", telefono="", placa="", tipo_servicio="", fecha_solicitada="", descripcion=""):
    """Valida el contrato de datos, calcula la clave y clasifica la solicitud."""
    solicitante = (solicitante or "").strip()
    telefono = (telefono or "").replace(" ", "").strip()
    placa = (placa or "").strip().upper()
    tipo_servicio = (tipo_servicio or "").strip().lower()
    fecha_solicitada = (fecha_solicitada or "").strip()
    descripcion = (descripcion or "").strip()

    errores = []
    if not solicitante:
        errores.append(_error_campo_faltante("solicitante"))
    if not telefono:
        errores.append(_error_campo_faltante("telefono"))
    elif not PATRON_TELEFONO.match(telefono):
        errores.append(comun.error(
            "TELEFONO_INVALIDO",
            "El telefono no es valido.",
            "Pedir un telefono de 9 digitos que empiece en 9.",
        ))
    if not placa:
        errores.append(_error_campo_faltante("placa"))
    elif not PATRON_PLACA.match(placa):
        errores.append(comun.error(
            "PLACA_INVALIDA",
            "La placa no tiene el formato correcto.",
            "Pedir la placa con el formato T4M-891.",
        ))
    if not tipo_servicio:
        errores.append(_error_campo_faltante("tipo_servicio"))
    elif tipo_servicio not in TIPOS_SERVICIO:
        errores.append(comun.error(
            "TIPO_INVALIDO",
            "Ese tipo de servicio no existe.",
            "Ofrecer preventivo_5000, preventivo_10000 o preventivo_20000.",
        ))
    if not fecha_solicitada:
        errores.append(_error_campo_faltante("fecha_solicitada"))
    elif not PATRON_FECHA.match(fecha_solicitada):
        errores.append(comun.error(
            "FECHA_INVALIDA",
            "La fecha no es valida.",
            "Pedir una fecha desde hoy, formato AAAA-MM-DD.",
        ))
    else:
        try:
            fecha = date.fromisoformat(fecha_solicitada)
        except ValueError:
            errores.append(comun.error(
                "FECHA_INVALIDA",
                "La fecha no es valida.",
                "Pedir una fecha desde hoy, formato AAAA-MM-DD.",
            ))
        else:
            if fecha < config.hoy():
                errores.append(comun.error(
                    "FECHA_INVALIDA",
                    "La fecha no es valida.",
                    "Pedir una fecha desde hoy, formato AAAA-MM-DD.",
                ))

    clave = ""
    if placa and fecha_solicitada and tipo_servicio:
        clave = calcular_clave(placa, fecha_solicitada, tipo_servicio)

    if errores:
        resultado = {"ok": False, "clase": "datos", "errores": errores}
        with comun.transaccion(conn):
            comun.registrar_bitacora(conn, clave, "validar_solicitud", errores[0]["codigo"])
        return resultado

    datos = {
        "solicitante": solicitante,
        "telefono": telefono,
        "placa": placa,
        "tipo_servicio": tipo_servicio,
        "fecha_solicitada": fecha_solicitada,
        "descripcion": descripcion,
        "canal": "web",
    }
    with comun.transaccion(conn):
        conn.execute(
            "INSERT OR REPLACE INTO solicitudes_validadas (clave, datos_json, creada_en) VALUES (?, ?, ?)",
            (clave, json.dumps(datos, ensure_ascii=False), comun.ahora_texto()),
        )

    fila_cita = conn.execute(
        "SELECT id_cita, fecha, hora, bahia, tecnico FROM citas WHERE clave = ?", (clave,)
    ).fetchone()
    if fila_cita is not None:
        resultado = {
            "ok": True,
            "estado": "ya_existe",
            "cita": {
                "id_cita": fila_cita["id_cita"],
                "fecha": fila_cita["fecha"],
                "hora": fila_cita["hora"],
                "bahia": fila_cita["bahia"],
                "tecnico": fila_cita["tecnico"],
            },
            "que_hacer": "Informa al cliente que su cita ya existe con esos datos y su codigo (id_cita), y no crees otra.",
        }
    elif _tiene_palabra_de_falla(descripcion):
        resultado = {
            "ok": True,
            "estado": "posible_falla",
            "clave": clave,
            "que_hacer": (
                "Llama derivar_a_humano con motivo='POSIBLE_CORRECTIVO' y la clave. "
                "Explica que parece una reparación y ofrece cotizarla."
            ),
        }
    else:
        resultado = {
            "ok": True,
            "estado": "valida",
            "clave": clave,
            "que_hacer": "Llama consultar_disponibilidad con la clave.",
        }

    with comun.transaccion(conn):
        comun.registrar_bitacora(conn, clave, "validar_solicitud", "OK")
    return resultado


def _alternativas(conn, fecha):
    filas = conn.execute(
        "SELECT DISTINCT fecha FROM agenda WHERE fecha > ? AND estado = 'libre' ORDER BY fecha LIMIT 3",
        (fecha,),
    ).fetchall()
    alternativas = []
    for fila in filas:
        hueco = conn.execute(
            "SELECT hora FROM agenda WHERE fecha = ? AND estado = 'libre' ORDER BY hora, bahia LIMIT 1",
            (fila["fecha"],),
        ).fetchone()
        alternativas.append({"fecha": fila["fecha"], "hora": hueco["hora"]})
    return alternativas


def _verificar_disponibilidad(conn, clave, datos):
    fecha = datos["fecha_solicitada"]
    tipo_servicio = datos["tipo_servicio"]

    rango = conn.execute("SELECT MIN(fecha) AS minima, MAX(fecha) AS maxima FROM agenda").fetchone()
    if fecha < rango["minima"] or fecha > rango["maxima"]:
        return comun.error(
            "FECHA_SIN_AGENDA",
            "No hay agenda para esa fecha.",
            f"Pedir una fecha entre {rango['minima']} y {rango['maxima']}.",
        )

    kit = conn.execute(
        "SELECT kit_codigo, stock, duracion_horas FROM kits WHERE tipo_servicio = ?", (tipo_servicio,)
    ).fetchone()
    if kit is None or kit["stock"] <= 0:
        return comun.error(
            "SIN_KIT",
            "No hay kit disponible.",
            "Llama derivar_a_humano con motivo='SIN_KIT' y la clave. Explica que ese servicio no tiene kit "
            "disponible por ahora (no depende de la fecha) y que un asesor lo contactará; no digas que la "
            "solicitud o la cita fue registrada.",
        )

    hueco = conn.execute(
        "SELECT hora, bahia, tecnico FROM agenda WHERE fecha = ? AND estado = 'libre' ORDER BY hora, bahia LIMIT 1",
        (fecha,),
    ).fetchone()
    if hueco is None:
        alternativas = _alternativas(conn, fecha)
        return comun.error(
            "SIN_CUPO",
            "No hay cupo en esa fecha.",
            (
                "Ofrece al cliente las 3 fechas copiando el campo alternativas_texto tal cual, "
                "sin traducirlo ni reformatearlo. Si el cliente elige una, llama validar_solicitud "
                "otra vez con la misma información y la fecha nueva."
            ),
            alternativas=alternativas,
            alternativas_texto=", ".join(
                f"{alternativa['fecha']} {alternativa['hora']}" for alternativa in alternativas
            ),
        )

    if kit["duracion_horas"] > 2:
        return comun.error(
            "REQUIERE_APROBACION",
            "Este servicio necesita aprobacion del jefe de taller.",
            "Llama derivar_a_humano con motivo='REQUIERE_APROBACION' y la clave; explica que lo aprueba el jefe de taller.",
        )

    return {
        "ok": True,
        "hora": hueco["hora"],
        "bahia": hueco["bahia"],
        "tecnico": hueco["tecnico"],
        "kit": kit["kit_codigo"],
        "duracion_horas": kit["duracion_horas"],
        "que_hacer": "Llama preparar_cita con la clave.",
    }


def consultar_disponibilidad(conn, clave):
    """Verifica fecha de agenda, kit, cupo y duracion para una clave validada."""
    datos = _solicitud(conn, clave)
    if datos is None:
        resultado = comun.error(
            "CLAVE_DESCONOCIDA",
            "No hay una solicitud guardada con esa clave.",
            "Llama validar_solicitud primero.",
        )
    else:
        resultado = _verificar_disponibilidad(conn, clave, datos)
    _registrar(conn, clave, "consultar_disponibilidad", resultado)
    return resultado


def preparar_cita(conn, clave):
    """Repite las verificaciones y emite el testigo de confirmacion."""
    datos = _solicitud(conn, clave)
    if datos is None:
        resultado = comun.error(
            "CLAVE_DESCONOCIDA",
            "No hay una solicitud guardada con esa clave.",
            "Llama validar_solicitud primero.",
        )
        _registrar(conn, clave, "preparar_cita", resultado)
        return resultado

    verificacion = _verificar_disponibilidad(conn, clave, datos)
    if not verificacion.get("ok"):
        _registrar(conn, clave, "preparar_cita", verificacion)
        return verificacion

    with comun.transaccion(conn):
        testigo = comun.emitir_testigo(conn, "cita", clave)
        comun.registrar_bitacora(conn, clave, "preparar_cita", "OK")
    return {
        "ok": True,
        "resumen": {
            "placa": datos["placa"],
            "tipo_servicio": datos["tipo_servicio"],
            "fecha": datos["fecha_solicitada"],
            "hora": verificacion["hora"],
            "bahia": verificacion["bahia"],
            "tecnico": verificacion["tecnico"],
        },
        "testigo": testigo,
        "que_hacer": (
            "Muestra el resumen al cliente y pide que confirme. "
            "NO llames confirmar_cita hasta que el cliente responda en un mensaje nuevo."
        ),
    }


def _siguiente_id_cita(conn):
    fila = conn.execute("SELECT MAX(id_cita) AS maxima FROM citas").fetchone()
    if fila["maxima"] is None:
        return "CITA-0001"
    return f"CITA-{int(fila['maxima'].split('-')[1]) + 1:04d}"


def confirmar_cita(conn, testigo):
    """Consume el testigo y registra la cita bajando el cupo y el stock."""
    with comun.transaccion(conn):
        fila_testigo = comun.consumir_testigo(conn, testigo, "cita")
        if fila_testigo is None:
            comun.registrar_bitacora(conn, "", "confirmar_cita", "TESTIGO_INVALIDO")
            return comun.error("TESTIGO_INVALIDO", "El testigo no es valido.", "Vuelve a llamar preparar_cita")

        clave = fila_testigo["clave"]
        fila_cita = conn.execute(
            "SELECT id_cita, fecha, hora, bahia, tecnico FROM citas WHERE clave = ?", (clave,)
        ).fetchone()
        if fila_cita is not None:
            comun.registrar_bitacora(conn, clave, "confirmar_cita", "OK")
            return {
                "ok": True,
                "estado": "ya_existe",
                "cita": {
                    "id_cita": fila_cita["id_cita"],
                    "fecha": fila_cita["fecha"],
                    "hora": fila_cita["hora"],
                    "bahia": fila_cita["bahia"],
                    "tecnico": fila_cita["tecnico"],
                },
                "que_hacer": "Informa al cliente que su cita ya existe con esos datos y su codigo (id_cita), y no crees otra.",
            }

        datos = _solicitud(conn, clave)
        verificacion = _verificar_disponibilidad(conn, clave, datos)
        if not verificacion.get("ok"):
            comun.registrar_bitacora(conn, clave, "confirmar_cita", verificacion["codigo"])
            return verificacion

        conn.execute(
            "UPDATE agenda SET estado = 'ocupado' WHERE fecha = ? AND hora = ? AND bahia = ? AND estado = 'libre'",
            (datos["fecha_solicitada"], verificacion["hora"], verificacion["bahia"]),
        )
        conn.execute(
            "UPDATE kits SET stock = stock - 1 WHERE tipo_servicio = ?", (datos["tipo_servicio"],)
        )
        id_cita = _siguiente_id_cita(conn)
        conn.execute(
            "INSERT INTO citas (id_cita, clave, placa, fecha, hora, bahia, tecnico, tipo_servicio,"
            " solicitante, telefono, descripcion, canal, estado, creada_en)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                id_cita,
                clave,
                datos["placa"],
                datos["fecha_solicitada"],
                verificacion["hora"],
                verificacion["bahia"],
                verificacion["tecnico"],
                datos["tipo_servicio"],
                datos["solicitante"],
                datos["telefono"],
                datos["descripcion"],
                "web",
                "confirmada",
                comun.ahora_texto(),
            ),
        )
        comun.registrar_bitacora(conn, clave, "confirmar_cita", "OK")
        return {
            "ok": True,
            "id_cita": id_cita,
            "fecha": datos["fecha_solicitada"],
            "hora": verificacion["hora"],
            "bahia": verificacion["bahia"],
            "tecnico": verificacion["tecnico"],
            "que_hacer": "Confirma la cita e incluye su codigo (id_cita), fecha y hora.",
        }


QUE_HACER_FUERA_DE_ALCANCE = (
    "Explica al cliente que no puedes cancelar ni reprogramar citas desde este chat y que un asesor "
    "lo contactara; termina tu respuesta sin llamar mas herramientas."
)


def derivar_a_humano(conn, motivo, consulta_original, clave=""):
    """Encola la consulta para un asesor con la solicitud y los pasos previos."""
    motivo = (motivo or "").strip().upper()
    if motivo not in MOTIVOS_DERIVACION:
        motivo = "OTRO"
    with comun.transaccion(conn):
        resultado = comun.derivar(conn, "citas", motivo, consulta_original, clave)
        comun.registrar_bitacora(conn, clave, "derivar_a_humano", "OK")
    if motivo == "FUERA_DE_ALCANCE":
        resultado["que_hacer"] = QUE_HACER_FUERA_DE_ALCANCE
    return resultado
