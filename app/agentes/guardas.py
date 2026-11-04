"""Guardas: testigos del turno, limite de iteraciones, salidas invalidas y errores."""
import contextvars
import json
import traceback

from langchain_core.tools import StructuredTool
from langgraph.errors import GraphRecursionError

from app.agentes import mcp_clientes, trazas

MENSAJE_DERIVADO = "No pude completar tu solicitud. Un asesor la revisará."
MENSAJE_MODELO_APAGADO = "No puedo responder ahora porque el modelo no está encendido."
MENSAJE_ERROR = "Tuve un problema para procesar tu mensaje. Inténtalo de nuevo."

ESPERAR_CONFIRMACION = {
    "ok": False,
    "codigo": "ESPERAR_CONFIRMACION",
    "mensaje": "El cliente todavía no confirmó.",
    "que_hacer": "Muestra el resumen al cliente, pide que confirme y termina tu respuesta. No llames más herramientas.",
    "clase": "datos",
}

EMISORAS = ("preparar_cita", "validar_politica_comercial")
CONFIRMADORAS = ("confirmar_cita", "programar_servicio")

PREGUNTA_CONFIRMACION = "¿Confirmas que programe el servicio?"

HILO = contextvars.ContextVar("hilo_id", default="")
TESTIGOS = contextvars.ContextVar("testigos_del_turno", default=None)
_AGENTE = {"nombre": "citas"}
RESPUESTAS_CONFIRMACION = {}
PEDIR_CONFIRMACION = {}
ULTIMO_AGENTE = {}
FLUJO_ABIERTO = {}


def iniciar_turno(hilo_id):
    """Fija el hilo del turno y vacia el conjunto de testigos emitidos."""
    HILO.set(hilo_id)
    TESTIGOS.set(set())
    PEDIR_CONFIRMACION[hilo_id] = False


def hilo_actual():
    """El hilo de la conversacion en curso."""
    return HILO.get()


def fijar_agente(nombre):
    """Anota que agente quedo activo en este turno (visible fuera de las tareas internas)."""
    _AGENTE["nombre"] = nombre
    if hilo_actual():
        ULTIMO_AGENTE[hilo_actual()] = nombre
        FLUJO_ABIERTO[hilo_actual()] = True


def ultimo_agente(hilo):
    """El ultimo agente que atendio ese hilo, si alguno."""
    return ULTIMO_AGENTE.get(hilo)


def flujo_abierto(hilo):
    """Si el hilo quedo en medio de un flujo sin cierre en OK."""
    return FLUJO_ABIERTO.get(hilo, False)


def agente_actual():
    """El agente activo del turno en curso."""
    return _AGENTE["nombre"]


def anotar_respuesta(texto):
    """Anota si la ultima respuesta pidio al cliente confirmar con una pregunta."""
    RESPUESTAS_CONFIRMACION[hilo_actual()] = "confirm" in (texto or "").lower() and "?" in (texto or "")


def pidio_confirmacion():
    """Si la ultima respuesta del hilo pidio al cliente confirmar."""
    return RESPUESTAS_CONFIRMACION.get(hilo_actual(), False)


def asegurar_pregunta(texto):
    """Agrega la pregunta de confirmacion si la guarda bloqueo programar y el modelo no la hizo."""
    hilo = hilo_actual()
    if not PEDIR_CONFIRMACION.get(hilo):
        return texto
    PEDIR_CONFIRMACION[hilo] = False
    if "confirm" in (texto or "").lower() and "?" in (texto or ""):
        return texto
    return f"{texto.rstrip()}\n\n{PREGUNTA_CONFIRMACION}"


def turno_actual():
    """Testigos emitidos en el turno actual."""
    return _turno()


def _turno():
    conjunto = TESTIGOS.get()
    if conjunto is None:
        conjunto = set()
        TESTIGOS.set(conjunto)
    return conjunto


def _cuerpo(resultado):
    """El diccionario interno del resultado JSON de una herramienta, si se puede leer."""
    carga = resultado
    if isinstance(carga, list):
        for bloque in carga:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                carga = bloque.get("text", "")
                break
        else:
            return None
    if isinstance(carga, dict):
        return carga
    if isinstance(carga, str):
        try:
            datos = json.loads(carga)
        except ValueError:
            return None
        if isinstance(datos, dict):
            return datos
    return None


def _cerrar_si_ok(resultado):
    if (_cuerpo(resultado) or {}).get("ok") is True:
        FLUJO_ABIERTO[hilo_actual()] = False


def _envolver_emisora(herramienta):
    async def llamada(**kwargs):
        resultado = await herramienta.ainvoke(kwargs)
        datos = _cuerpo(resultado)
        if datos and datos.get("testigo"):
            _turno().add(datos["testigo"])
        return resultado

    return StructuredTool.from_function(
        coroutine=llamada,
        name=herramienta.name,
        description=herramienta.description,
        args_schema=herramienta.args_schema,
    )


def _envolver_confirmadora(herramienta, exige_confirmacion=False):
    async def llamada(**kwargs):
        testigo = (kwargs or {}).get("testigo")
        if testigo and testigo in _turno():
            return json.dumps(ESPERAR_CONFIRMACION, ensure_ascii=False)
        if testigo and exige_confirmacion and not pidio_confirmacion():
            PEDIR_CONFIRMACION[hilo_actual()] = True
            return json.dumps(ESPERAR_CONFIRMACION, ensure_ascii=False)
        resultado = await herramienta.ainvoke(kwargs)
        _cerrar_si_ok(resultado)
        return resultado

    return StructuredTool.from_function(
        coroutine=llamada,
        name=herramienta.name,
        description=herramienta.description,
        args_schema=herramienta.args_schema,
    )


def _envolver_cierre(herramienta):
    """Envuelve una herramienta que cierra el flujo del hilo cuando responde OK."""
    async def llamada(**kwargs):
        resultado = await herramienta.ainvoke(kwargs)
        _cerrar_si_ok(resultado)
        return resultado

    return StructuredTool.from_function(
        coroutine=llamada,
        name=herramienta.name,
        description=herramienta.description,
        args_schema=herramienta.args_schema,
    )


def aplicar_guardas(herramientas):
    """Envuelve las herramientas de un agente con la guarda de turno."""
    envueltas = []
    for herramienta in herramientas:
        if herramienta.name in EMISORAS:
            envueltas.append(_envolver_emisora(herramienta))
        elif herramienta.name in CONFIRMADORAS:
            envueltas.append(
                _envolver_confirmadora(herramienta, exige_confirmacion=herramienta.name == "programar_servicio")
            )
        elif herramienta.name == "derivar_a_humano":
            envueltas.append(_envolver_cierre(herramienta))
        else:
            envueltas.append(herramienta)
    return envueltas


async def ejecutar(agente, config, mensaje):
    """Invoca al agente con las guardas de recursion y de salida invalida."""
    try:
        resultado = await agente.ainvoke({"messages": [("user", mensaje)]}, config=config)
    except GraphRecursionError:
        await derivar("LIMITE_DE_ITERACIONES", mensaje)
        anotar_respuesta(MENSAJE_DERIVADO)
        return MENSAJE_DERIVADO
    texto = texto_de(resultado)
    if _salida_valida(texto):
        texto = asegurar_pregunta(texto)
        anotar_respuesta(texto)
        return texto
    try:
        resultado = await agente.ainvoke({"messages": [("user", mensaje)]}, config=config)
    except GraphRecursionError:
        await derivar("LIMITE_DE_ITERACIONES", mensaje)
        anotar_respuesta(MENSAJE_DERIVADO)
        return MENSAJE_DERIVADO
    texto = texto_de(resultado)
    if _salida_valida(texto):
        texto = asegurar_pregunta(texto)
        anotar_respuesta(texto)
        return texto
    await derivar("ERROR_DE_SISTEMA", mensaje)
    anotar_respuesta(MENSAJE_DERIVADO)
    return MENSAJE_DERIVADO


def texto_de(resultado):
    """Texto de la ultima respuesta del agente."""
    if not isinstance(resultado, dict) or not resultado.get("messages"):
        return ""
    contenido = resultado["messages"][-1].content
    if isinstance(contenido, str):
        return contenido.strip()
    partes = []
    for bloque in contenido or []:
        if isinstance(bloque, str):
            partes.append(bloque)
        elif isinstance(bloque, dict) and bloque.get("type") == "text":
            partes.append(bloque.get("text", ""))
    return "".join(partes).strip()


def _salida_valida(texto):
    if not texto:
        return False
    return "<tool_call>" not in texto and "<think>" not in texto


async def derivar(motivo, consulta_original):
    """Deriva la consulta al asesor usando el servidor del agente activo."""
    servidor = "cotizaciones" if agente_actual() == "cotizacion" else "citas"
    try:
        herramientas = await mcp_clientes.cargar(servidor)
        herramienta = next((h for h in herramientas if h.name == "derivar_a_humano"), None)
        if herramienta is not None:
            resultado = await herramienta.ainvoke({"motivo": motivo, "consulta_original": consulta_original})
            _cerrar_si_ok(resultado)
    except Exception as excepcion:
        registrar_error(excepcion)


def registrar_error(excepcion):
    """Anota un error inesperado, con su traceback, en var/trazas.jsonl."""
    trazas.registrar({
        "tipo": "error",
        "agente": agente_actual(),
        "herramienta": "",
        "argumentos": "",
        "codigo": type(excepcion).__name__,
        "detalle": "".join(traceback.format_exception(excepcion)),
    })
