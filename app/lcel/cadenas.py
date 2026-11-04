"""Cadenas LCEL explicitas: clasificacion de intencion y resumen de derivacion."""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from app.llm import get_llm

PROMPT_INTENCION = ChatPromptTemplate.from_messages([
    (
        "system",
        "Clasifica el mensaje del cliente en una sola palabra: citas, cotizacion u otro. "
        "citas = quiere agendar, cambiar o cancelar una cita de mantenimiento preventivo. "
        "cotizacion = pide el precio de una reparacion o describe una falla del vehiculo. "
        "otro = cualquier tema distinto. Responde solo la palabra, sin explicar.",
    ),
    ("human", "{mensaje}"),
])

cadena_intencion = PROMPT_INTENCION | get_llm() | StrOutputParser()


def _contexto_derivacion(datos):
    """Ordena los datos de la derivacion en los campos que lee el prompt."""
    return {
        "motivo": datos.get("motivo", ""),
        "consulta": datos.get("consulta_original", ""),
        "datos": datos.get("datos_obtenidos", "sin datos"),
        "pasos": datos.get("pasos", "sin pasos"),
    }


PROMPT_RESUMEN = ChatPromptTemplate.from_messages([
    (
        "system",
        "Resume en una sola linea, en espanol, por que se deriva el caso a una persona. "
        "No inventes datos. Devuelve solo la linea, sin comillas.",
    ),
    ("human", "Motivo: {motivo}\nConsulta: {consulta}\nDatos: {datos}\nPasos: {pasos}"),
])

cadena_resumen_derivacion = (
    RunnablePassthrough.assign(contexto=RunnableLambda(_contexto_derivacion))
    | RunnableLambda(lambda datos: datos["contexto"])
    | PROMPT_RESUMEN
    | get_llm()
    | StrOutputParser()
)
