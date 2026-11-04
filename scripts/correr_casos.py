"""Casos de prueba del chat (especificacion 05): corre los 14 casos contra la API y deja la evidencia."""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import comun, db
from app.agentes import trazas
from app.mcp_citas import logica as logica_citas

URL_POR_DEFECTO = "http://127.0.0.1:8000"
CLAVE_ESPERADA = "1b114e68d6a3241784560e39cf0868d9"
RUTA_EVIDENCIAS = RAIZ / "evidencias"


def plano(texto):
    """Minusculas sin tildes para comparar palabras clave."""
    return logica_citas.sin_tildes((texto or "").lower())


def sin_comas(texto):
    return plano(texto).replace(",", "")


def celda(texto):
    """Prepara un texto para una celda de tabla Markdown."""
    return str(texto if texto is not None else "").replace("|", "\\|").replace("\n", "<br>").strip()


def enviar(url, mensaje, hilo):
    """Envia un mensaje por POST /api/chat y devuelve la respuesta del asistente."""
    cuerpo = json.dumps({"mensaje": mensaje, "hilo_id": hilo}).encode("utf-8")
    peticion = urllib.request.Request(
        f"{url}/api/chat",
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=180) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))["respuesta"]
    except (urllib.error.URLError, TimeoutError, OSError) as excepcion:
        raise SystemExit(f"No pude hablar con la API en {url}: {excepcion}")


def lineas_trazas():
    if not trazas.RUTA_TRAZAS.exists():
        return []
    with open(trazas.RUTA_TRAZAS, encoding="utf-8") as archivo:
        return archivo.readlines()


def eventos_desde(corte, hilo):
    """Eventos de var/trazas.jsonl escritos despues del corte, del hilo indicado."""
    eventos = []
    for linea in lineas_trazas()[corte:]:
        try:
            evento = json.loads(linea)
        except ValueError:
            continue
        if evento.get("hilo_id") == hilo:
            eventos.append(evento)
    return eventos


def correr_turno(url, hilo, mensaje):
    corte = len(lineas_trazas())
    respuesta = enviar(url, mensaje, hilo)
    return {"mensaje": mensaje, "respuesta": respuesta, "eventos": eventos_desde(corte, hilo)}


def foto_bases():
    """Estado de las dos bases SQLite para comparar antes y despues de un caso."""
    with db.abrir_proceso1() as conn:
        citas = [
            dict(fila)
            for fila in conn.execute(
                "SELECT id_cita, placa, fecha, hora, bahia, tipo_servicio, solicitante, estado"
                " FROM citas ORDER BY id_cita"
            )
        ]
        cola1 = conn.execute("SELECT COUNT(*) AS total FROM cola_excepciones").fetchone()["total"]
        agenda = {
            (fila["fecha"], fila["hora"], fila["bahia"]): fila["estado"]
            for fila in conn.execute("SELECT fecha, hora, bahia, estado FROM agenda")
        }
    with db.abrir_proceso2() as conn:
        cola2 = conn.execute("SELECT COUNT(*) AS total FROM cola_excepciones").fetchone()["total"]
        cotizaciones = [
            dict(fila)
            for fila in conn.execute(
                "SELECT id_cotizacion, total, estado FROM cotizaciones ORDER BY id_cotizacion"
            )
        ]
        ordenes = [
            dict(fila)
            for fila in conn.execute("SELECT id_ot, id_cotizacion FROM ordenes_trabajo ORDER BY id_ot")
        ]
    return {
        "citas1": citas,
        "cola1": cola1,
        "agenda": agenda,
        "cola2": cola2,
        "cotizaciones2": cotizaciones,
        "ordenes2": ordenes,
    }


def llamadas(turno, nombre=None):
    return [
        evento
        for evento in turno["eventos"]
        if evento.get("tipo") == "herramienta" and (nombre is None or evento.get("herramienta") == nombre)
    ]


def hubo(turno, nombre, codigo=None):
    eventos = llamadas(turno, nombre)
    if codigo is None:
        return bool(eventos)
    return any(evento.get("codigo") == codigo for evento in eventos)


def ultimo_evento(turno, nombre):
    eventos = llamadas(turno, nombre)
    return eventos[-1] if eventos else None


def resultado_de(evento):
    return (evento or {}).get("resultado") or {}


def argumentos_de(evento):
    valor = (evento or {}).get("argumentos") or ""
    if isinstance(valor, dict):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def tiene_motivo(evento, motivo):
    return motivo in argumentos_de(evento)


def descuento_solicitado(evento):
    coincidencia = re.search(r"descuento_solicitado_pct[^0-9]*([0-9]+(?:\.[0-9]+)?)", argumentos_de(evento))
    if coincidencia:
        return float(coincidencia.group(1))
    return 0.0


def citas_nuevas(antes, despues):
    ids = {fila["id_cita"] for fila in antes["citas1"]}
    return [fila for fila in despues["citas1"] if fila["id_cita"] not in ids]


def verificar_p1_01(datos):
    turno1, turno2 = datos["turnos"]
    nueva = next(
        (fila for fila in citas_nuevas(datos["antes"], datos["despues"]) if fila["id_cita"] == "CITA-0002"),
        None,
    )
    return [
        ("Turno 1: validar_solicitud(OK)", hubo(turno1, "validar_solicitud", "OK")),
        ("Turno 1: preparar_cita(OK)", hubo(turno1, "preparar_cita", "OK")),
        ("Turno 1: no se llamó confirmar_cita", not hubo(turno1, "confirmar_cita")),
        ('Turno 1: la respuesta contiene "08:00"', "08:00" in turno1["respuesta"]),
        ("Turno 2: confirmar_cita(OK)", hubo(turno2, "confirmar_cita", "OK")),
        (
            "La tabla citas tiene CITA-0002 con placa A1B-234, fecha 2026-10-21 y hora 08:00",
            nueva is not None
            and nueva["placa"] == "A1B-234"
            and nueva["fecha"] == "2026-10-21"
            and nueva["hora"] == "08:00",
        ),
        (
            'La hora 2026-10-21 08:00 quedó "ocupado"',
            datos["despues"]["agenda"].get(("2026-10-21", "08:00", "B1")) == "ocupado",
        ),
    ]


def verificar_p1_02(datos):
    turno1 = datos["turnos"][0]
    evento = ultimo_evento(turno1, "validar_solicitud")
    return [
        ("validar_solicitud devolvió estado ya_existe", resultado_de(evento).get("estado") == "ya_existe"),
        ("No se llamó preparar_cita", not hubo(turno1, "preparar_cita")),
        ("No se llamó confirmar_cita", not hubo(turno1, "confirmar_cita")),
        (
            "La tabla citas no cambió de tamaño",
            len(datos["despues"]["citas1"]) == len(datos["antes"]["citas1"]),
        ),
        ('La respuesta contiene "CITA-0001"', "CITA-0001" in turno1["respuesta"]),
    ]


def verificar_p1_03(datos):
    turno1 = datos["turnos"][0]
    return [
        (
            "consultar_disponibilidad o preparar_cita devolvió SIN_CUPO",
            hubo(turno1, "consultar_disponibilidad", "SIN_CUPO") or hubo(turno1, "preparar_cita", "SIN_CUPO"),
        ),
        ("La respuesta contiene 2026-10-23", "2026-10-23" in turno1["respuesta"]),
        ("La respuesta contiene 2026-10-26", "2026-10-26" in turno1["respuesta"]),
        ("La respuesta contiene 2026-10-27", "2026-10-27" in turno1["respuesta"]),
        ("No se creó cita", len(datos["despues"]["citas1"]) == len(datos["antes"]["citas1"])),
    ]


def verificar_p1_04(datos):
    turno1 = datos["turnos"][0]
    derivacion = ultimo_evento(turno1, "derivar_a_humano")
    return [
        (
            "consultar_disponibilidad o preparar_cita devolvió SIN_KIT",
            hubo(turno1, "consultar_disponibilidad", "SIN_KIT") or hubo(turno1, "preparar_cita", "SIN_KIT"),
        ),
        ("derivar_a_humano llamado con motivo SIN_KIT", tiene_motivo(derivacion, "SIN_KIT")),
        (
            "cola_excepciones del proceso 1 creció en 1",
            datos["despues"]["cola1"] == datos["antes"]["cola1"] + 1,
        ),
        ("No se creó cita", len(datos["despues"]["citas1"]) == len(datos["antes"]["citas1"])),
    ]


def verificar_p1_05(datos):
    turno1 = datos["turnos"][0]
    derivacion = ultimo_evento(turno1, "derivar_a_humano")
    return [
        ("consultar_disponibilidad devolvió REQUIERE_APROBACION", hubo(turno1, "consultar_disponibilidad", "REQUIERE_APROBACION")),
        ("derivar_a_humano llamado con motivo REQUIERE_APROBACION", tiene_motivo(derivacion, "REQUIERE_APROBACION")),
        (
            "cola_excepciones del proceso 1 creció en 1",
            datos["despues"]["cola1"] == datos["antes"]["cola1"] + 1,
        ),
        ("No se creó cita", len(datos["despues"]["citas1"]) == len(datos["antes"]["citas1"])),
    ]


def verificar_p1_06(datos):
    turno1 = datos["turnos"][0]
    evento = ultimo_evento(turno1, "validar_solicitud")
    codigos = {error.get("codigo") for error in resultado_de(evento).get("errores") or []}
    esperados = {"PLACA_INVALIDA", "TIPO_INVALIDO", "FECHA_INVALIDA", "TELEFONO_INVALIDO"}
    return [
        ("validar_solicitud devolvió los 4 códigos en una sola respuesta", esperados <= codigos),
        ("No se llamó consultar_disponibilidad", not hubo(turno1, "consultar_disponibilidad")),
    ]


def verificar_p1_07(datos):
    turno1 = datos["turnos"][0]
    evento = ultimo_evento(turno1, "validar_solicitud")
    derivacion = ultimo_evento(turno1, "derivar_a_humano")
    return [
        ("validar_solicitud devolvió estado posible_falla", resultado_de(evento).get("estado") == "posible_falla"),
        ("derivar_a_humano llamado con motivo POSIBLE_CORRECTIVO", tiene_motivo(derivacion, "POSIBLE_CORRECTIVO")),
        ("No se creó cita", len(datos["despues"]["citas1"]) == len(datos["antes"]["citas1"])),
    ]


def verificar_p1_08(datos):
    turno1 = datos["turnos"][0]
    agenda = {
        evento["herramienta"]
        for evento in llamadas(turno1)
        if evento["herramienta"] in trazas.HERRAMIENTAS_CITAS
    }
    derivacion = ultimo_evento(turno1, "derivar_a_humano")
    respuesta = plano(turno1["respuesta"])
    return [
        ("No se usaron herramientas de agenda", agenda == set()),
        ("derivar_a_humano(OK)", hubo(turno1, "derivar_a_humano", "OK")),
        ("derivar_a_humano llamado con motivo FUERA_DE_ALCANCE", tiene_motivo(derivacion, "FUERA_DE_ALCANCE")),
        ('La respuesta contiene "no puedo"', "no puedo" in respuesta),
        ("No se creó ni cambió ninguna cita", datos["despues"]["citas1"] == datos["antes"]["citas1"]),
    ]


def verificar_p2_01(datos):
    turno1 = datos["turnos"][0]
    tarifario = ultimo_evento(turno1, "consultar_tarifario")
    codigos = {coincidencia.get("codigo") for coincidencia in resultado_de(tarifario).get("coincidencias") or []}
    cotizacion = next(
        (fila for fila in datos["despues"]["cotizaciones2"] if fila["id_cotizacion"] == "COT-0001"), None
    )
    return [
        (
            "consultar_tarifario(OK) con FRE-01 en las coincidencias",
            hubo(turno1, "consultar_tarifario", "OK") and "FRE-01" in codigos,
        ),
        ("armar_cotizacion(OK)", hubo(turno1, "armar_cotizacion", "OK")),
        ("validar_politica_comercial(OK)", hubo(turno1, "validar_politica_comercial", "OK")),
        ('La respuesta contiene "270"', "270" in plano(turno1["respuesta"])),
        (
            "cotizaciones tiene COT-0001 en estado validada",
            cotizacion is not None and cotizacion["estado"] == "validada",
        ),
    ]


def verificar_p2_02(datos):
    turno = datos["turnos"][0]
    politica = ultimo_evento(turno, "validar_politica_comercial")
    aviso = (resultado_de(politica).get("aviso") or {}).get("codigo")
    return [
        ("validar_politica_comercial llamado con descuento mayor a 0", descuento_solicitado(politica) > 0),
        ("El aviso es DESCUENTO_NO_PERMITIDO", aviso == "DESCUENTO_NO_PERMITIDO"),
        ('La respuesta contiene "270"', "270" in plano(turno["respuesta"])),
        (
            "No hay cotización nueva",
            len(datos["despues"]["cotizaciones2"]) == len(datos["antes"]["cotizaciones2"]),
        ),
    ]


def verificar_p2_03(datos):
    turno3, turno4 = datos["turnos"]
    orden = next((fila for fila in datos["despues"]["ordenes2"] if fila["id_ot"] == "OT-0001"), None)
    cotizacion = next(
        (fila for fila in datos["despues"]["cotizaciones2"] if fila["id_cotizacion"] == "COT-0001"), None
    )
    return [
        ("Turno 3: no se programó el servicio (sin llamada OK)", not hubo(turno3, "programar_servicio", "OK")),
        ('Turno 3: la respuesta pide confirmación', "confirm" in plano(turno3["respuesta"])),
        ("Tras el turno 3 no hay ninguna OT en ordenes_trabajo", datos["fotos"][0]["ordenes2"] == []),
        ("Turno 4: programar_servicio(OK)", hubo(turno4, "programar_servicio", "OK")),
        ("Existe OT-0001 ligada a COT-0001", orden is not None and orden["id_cotizacion"] == "COT-0001"),
        ("COT-0001 quedó aceptada", cotizacion is not None and cotizacion["estado"] == "aceptada"),
    ]


def verificar_p2_04(datos):
    turno1 = datos["turnos"][0]
    tarifario = ultimo_evento(turno1, "consultar_tarifario")
    codigos = {coincidencia.get("codigo") for coincidencia in resultado_de(tarifario).get("coincidencias") or []}
    derivacion = ultimo_evento(turno1, "derivar_a_humano")
    return [
        ("consultar_tarifario devolvió EMB-01 y DIS-01", {"EMB-01", "DIS-01"} <= codigos),
        (
            "validar_politica_comercial(MONTO_REQUIERE_APROBACION)",
            hubo(turno1, "validar_politica_comercial", "MONTO_REQUIERE_APROBACION"),
        ),
        (
            "derivar_a_humano llamado con motivo MONTO_REQUIERE_APROBACION",
            tiene_motivo(derivacion, "MONTO_REQUIERE_APROBACION"),
        ),
        ('La respuesta contiene "2500"', "2500" in sin_comas(turno1["respuesta"])),
        ("No se creó orden", len(datos["despues"]["ordenes2"]) == len(datos["antes"]["ordenes2"])),
    ]


def verificar_p2_05(datos):
    turno1 = datos["turnos"][0]
    return [
        ("consultar_tarifario(SERVICIO_NO_ENCONTRADO)", hubo(turno1, "consultar_tarifario", "SERVICIO_NO_ENCONTRADO")),
        ("No se llamó armar_cotizacion", not hubo(turno1, "armar_cotizacion")),
        (
            "La respuesta no contiene montos en soles ni en dólares",
            not re.search(r"(S/|\$)\s*\d", turno1["respuesta"]),
        ),
    ]


def verificar_p2_06(datos):
    turno1 = datos["turnos"][0]
    mcp = [
        evento
        for evento in llamadas(turno1)
        if evento.get("herramienta") in trazas.HERRAMIENTAS_CITAS
        or evento.get("herramienta") in trazas.HERRAMIENTAS_COTIZACION
    ]
    return [
        ("No se llamó ninguna herramienta de los servidores MCP", not mcp),
        ('La respuesta menciona "cita"', "cita" in plano(turno1["respuesta"])),
        ('La respuesta menciona "cotiz"', "cotiz" in plano(turno1["respuesta"])),
    ]


CASOS = (
    {
        "id": "P1-01",
        "escenario": "Cita sin problemas",
        "hilo": "p1-01",
        "mensajes": (
            "Quiero cita de preventivo 10000 para mi placa A1B-234 el 2026-10-21. Soy Marco Ruiz Delgado, telefono 987654321.",
            "Sí, confirmo.",
        ),
        "verificar": verificar_p1_01,
    },
    {
        "id": "P1-02",
        "escenario": "La cita ya existe (idempotencia)",
        "hilo": "p1-02",
        "mensajes": (
            "Cita preventivo_10000, placa T4M-891, 2026-10-20, Marco Ruiz Delgado, 987654321.",
        ),
        "verificar": verificar_p1_02,
    },
    {
        "id": "P1-03",
        "escenario": "Sin cupo: 3 fechas alternativas",
        "hilo": "p1-03",
        "mensajes": (
            "Preventivo_10000, placa B2C-345, fecha 2026-10-22, Ana Torres Rios, 912345678.",
        ),
        "verificar": verificar_p1_03,
    },
    {
        "id": "P1-04",
        "escenario": "Sin kit",
        "hilo": "p1-04",
        "mensajes": (
            "Preventivo_5000, placa C3D-456, 2026-10-21, Luis Pardo Soto, 923456789.",
        ),
        "verificar": verificar_p1_04,
    },
    {
        "id": "P1-05",
        "escenario": "Servicio de más de 2 horas",
        "hilo": "p1-05",
        "mensajes": (
            "Preventivo_20000, placa D4E-567, 2026-10-21, Rosa Diaz Luna, 934567890.",
        ),
        "verificar": verificar_p1_05,
    },
    {
        "id": "P1-06",
        "escenario": "Datos inválidos",
        "hilo": "p1-06",
        "mensajes": (
            "Placa ABC123, preventivo_15000, 2026-10-01, telefono 12345, me llamo Juan Perez.",
        ),
        "verificar": verificar_p1_06,
    },
    {
        "id": "P1-07",
        "escenario": "Falla en vez de preventivo",
        "hilo": "p1-07",
        "mensajes": (
            "Quiero cita de preventivo_10000, placa E5F-678, 2026-10-23, mi auto suena raro al frenar. Elena Rojas Paz, 945678901.",
        ),
        "verificar": verificar_p1_07,
    },
    {
        "id": "P1-08",
        "escenario": "Fuera de alcance",
        "hilo": "p1-08",
        "mensajes": (
            "Cancela mi cita de manana.",
        ),
        "verificar": verificar_p1_08,
    },
    {
        "id": "P2-01",
        "escenario": "Cotización simple",
        "hilo": "p2-01",
        "mensajes": (
            "Mi Toyota Hilux frena mal y hace ruido al frenar.",
        ),
        "verificar": verificar_p2_01,
    },
    {
        "id": "P2-02",
        "escenario": "Pide descuento",
        "hilo": "p2-01",
        "mensajes": (
            "Dame 10% de descuento en esa cotizacion.",
        ),
        "verificar": verificar_p2_02,
    },
    {
        "id": "P2-03",
        "escenario": "Acepta la cotización",
        "hilo": "p2-01",
        "mensajes": (
            "Esta bien, acepto la cotizacion de S/ 270.",
            "Sí, confirmo.",
        ),
        "verificar": verificar_p2_03,
    },
    {
        "id": "P2-04",
        "escenario": "Monto alto",
        "hilo": "p2-04",
        "mensajes": (
            "Mi camioneta necesita cambio de embrague y cambio de correa de distribucion.",
        ),
        "verificar": verificar_p2_04,
    },
    {
        "id": "P2-05",
        "escenario": "Servicio no encontrado",
        "hilo": "p2-05",
        "mensajes": (
            "Quiero que le pongan aire acondicionado nuevo a mi auto.",
        ),
        "verificar": verificar_p2_05,
    },
    {
        "id": "P2-06",
        "escenario": "Saludo y orquestador",
        "hilo": "p2-06",
        "mensajes": (
            "Hola, buenas tardes.",
        ),
        "verificar": verificar_p2_06,
    },
)


def pruebas_sin_modelo():
    """Pruebas de las herramientas sin modelo, al inicio de cada corrida."""
    pruebas = []
    clave = logica_citas.calcular_clave("T4M891", "2026-09-22", "preventivo_10000")
    pruebas.append({
        "nombre": "La clave de T4M891|2026-09-22|preventivo_10000",
        "detalle": clave,
        "pasa": clave == CLAVE_ESPERADA,
    })

    with db.abrir_proceso1() as conn:
        testigo = comun.emitir_testigo(conn, "cita", "PRUEBA-TESTIGO")
        comun.consumir_testigo(conn, testigo, "cita")
        confirmacion = logica_citas.confirmar_cita(conn, testigo)
    pruebas.append({
        "nombre": "Confirmar con un testigo ya usado devuelve TESTIGO_INVALIDO con que_hacer",
        "detalle": f"{confirmacion.get('codigo')}: {confirmacion.get('que_hacer', '')}",
        "pasa": confirmacion.get("codigo") == "TESTIGO_INVALIDO" and bool(confirmacion.get("que_hacer")),
    })

    with db.abrir_proceso1() as conn:
        primera = logica_citas.validar_solicitud(
            conn,
            solicitante="Prueba Doble",
            telefono="987000111",
            placa="X9X-999",
            tipo_servicio="preventivo_10000",
            fecha_solicitada="2026-10-27",
        )
        segunda = logica_citas.validar_solicitud(
            conn,
            solicitante="Prueba Doble",
            telefono="987000111",
            placa="X9X-999",
            tipo_servicio="preventivo_10000",
            fecha_solicitada="2026-10-27",
        )
        registros = conn.execute(
            "SELECT COUNT(*) AS total FROM solicitudes_validadas WHERE clave = ?", (primera.get("clave"),)
        ).fetchone()["total"]
    pruebas.append({
        "nombre": "Enviar dos veces la misma solicitud deja un solo registro",
        "detalle": f"clave {primera.get('clave')}, registros {registros}",
        "pasa": primera.get("clave") == segunda.get("clave") and registros == 1,
    })
    return pruebas


def correr_caso(caso, url, marca):
    """Corre los turnos de un caso y evalua sus aserciones."""
    hilo = f"caso-{caso['hilo']}-{marca}"
    antes = foto_bases()
    turnos = []
    fotos = []
    for mensaje in caso["mensajes"]:
        print(f"  [{caso['id']}] Cliente: {mensaje}")
        turno = correr_turno(url, hilo, mensaje)
        print(f"  [{caso['id']}] Asistente: {turno['respuesta']}")
        turnos.append(turno)
        fotos.append(foto_bases())
    despues = foto_bases()
    aserciones = caso["verificar"](
        {"turnos": turnos, "antes": antes, "despues": despues, "fotos": fotos}
    )
    return {
        "caso": caso,
        "turnos": turnos,
        "aserciones": aserciones,
        "pasa": all(aprobada for _, aprobada in aserciones),
    }


def escribir_evidencia(pruebas, resultados, url):
    """Escribe evidencias/AAAA-MM-DD_HHMM_resultados.md sin sobrescribir nada."""
    RUTA_EVIDENCIAS.mkdir(exist_ok=True)
    base = datetime.now().strftime("%Y-%m-%d_%H%M")
    ruta = RUTA_EVIDENCIAS / f"{base}_resultados.md"
    sufijo = 2
    while ruta.exists():
        ruta = RUTA_EVIDENCIAS / f"{base}_resultados_{sufijo}.md"
        sufijo += 1

    pasan = sum(1 for resultado in resultados if resultado["pasa"])
    lineas = [
        "# Resultados de los casos del chat",
        "",
        f"- Fecha y hora: {datetime.now().isoformat(sep=' ', timespec='seconds')}",
        f"- API: {url}",
        f"- Resumen: {pasan} de {len(resultados)} casos pasan",
        "",
        "## Pruebas sin modelo",
        "",
        "| Prueba | Detalle | Resultado |",
        "| --- | --- | --- |",
    ]
    for prueba in pruebas:
        lineas.append(
            f"| {celda(prueba['nombre'])} | {celda(prueba['detalle'])} |"
            f" {'PASA' if prueba['pasa'] else 'FALLA'} |"
        )
    lineas += [
        "",
        "## Casos",
        "",
        "| Caso | Escenario | Conversación | Herramientas llamadas | Aserciones | Resultado |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for resultado in resultados:
        conversacion = []
        for turno in resultado["turnos"]:
            conversacion.append(f"**Cliente:** {turno['mensaje']}")
            conversacion.append(f"**Asistente:** {turno['respuesta']}")
        herramientas = [
            f"{evento.get('agente', '')}: {evento['herramienta']} ({evento.get('codigo', '')})"
            for turno in resultado["turnos"]
            for evento in llamadas(turno)
        ]
        aserciones = [
            f"{'PASA' if aprobada else 'FALLA'} — {descripcion}"
            for descripcion, aprobada in resultado["aserciones"]
        ]
        lineas.append(
            "| {caso} | {escenario} | {conversacion} | {herramientas} | {aserciones} | {resultado_caso} |".format(
                caso=resultado["caso"]["id"],
                escenario=celda(resultado["caso"]["escenario"]),
                conversacion=celda("<br><br>".join(conversacion)),
                herramientas=celda("<br>".join(herramientas)) or "ninguna",
                aserciones=celda("<br>".join(aserciones)),
                resultado_caso="PASA" if resultado["pasa"] else "FALLA",
            )
        )
    lineas += ["", f"{pasan} de {len(resultados)} casos pasan.", ""]
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


def argumentos():
    analizador = argparse.ArgumentParser(description="Corre los casos de prueba del chat y guarda la evidencia.")
    analizador.add_argument(
        "--reiniciar",
        action="store_true",
        default=True,
        help="Reinicia los datos antes de empezar (activado por defecto).",
    )
    analizador.add_argument("--caso", default=None, help="Corre solo ese caso (por ejemplo P1-03), sin reiniciar.")
    analizador.add_argument("--url", default=URL_POR_DEFECTO, help=f"URL base de la API (por defecto {URL_POR_DEFECTO}).")
    return analizador.parse_args()


def main():
    opciones = argumentos()
    if opciones.reiniciar and opciones.caso is None:
        subprocess.run([sys.executable, str(RAIZ / "scripts" / "reiniciar_datos.py")], check=True)

    casos = [caso for caso in CASOS if opciones.caso is None or caso["id"] == opciones.caso]
    if not casos:
        raise SystemExit(f"No existe el caso {opciones.caso}.")

    pruebas = pruebas_sin_modelo()
    for prueba in pruebas:
        print(f"Sin modelo: {'PASA' if prueba['pasa'] else 'FALLA'} - {prueba['nombre']}")
    print()

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    resultados = []
    for caso in casos:
        print(f"[{caso['id']}] {caso['escenario']}")
        resultados.append(correr_caso(caso, opciones.url, marca))
        print()

    for resultado in resultados:
        print(f"{resultado['caso']['id']}: {'PASA' if resultado['pasa'] else 'FALLA'}")
        for descripcion, aprobada in resultado["aserciones"]:
            if not aprobada:
                print(f"    FALLA: {descripcion}")

    pasan = sum(1 for resultado in resultados if resultado["pasa"])
    ruta = escribir_evidencia(pruebas, resultados, opciones.url)
    print(f"\nEvidencia: {ruta}")
    print(f"{pasan} de {len(resultados)} casos pasan")
    if pasan != len(resultados) or not all(prueba["pasa"] for prueba in pruebas):
        sys.exit(1)


if __name__ == "__main__":
    main()
