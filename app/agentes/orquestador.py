"""Orquestador: recibe el mensaje del cliente y elige entre los dos agentes."""
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.tools import StructuredTool
from openai import APIConnectionError
from pydantic import BaseModel, Field

from app.agentes import MEMORIA, citas, cotizacion, guardas, prompts, trazas
from app.llm import comprobar_modelo, get_llm


class ConsultaCliente(BaseModel):
    consulta: str = Field(description="Mensaje del cliente copiado tal cual, sin resumir ni corregir.")


async def _llamar_citas(consulta: str) -> str:
    guardas.fijar_agente("citas")
    return await citas.consultar(consulta, guardas.hilo_actual())


async def _llamar_cotizacion(consulta: str) -> str:
    guardas.fijar_agente("cotizacion")
    return await cotizacion.consultar(consulta, guardas.hilo_actual())


HERRAMIENTAS = [
    StructuredTool.from_function(
        coroutine=_llamar_citas,
        name="agente_citas",
        description=(
            "Agenda una cita de mantenimiento preventivo. Úsala para agendar, cambiar o cancelar citas. "
            "NO la uses para cotizar reparaciones."
        ),
        args_schema=ConsultaCliente,
        return_direct=True,
    ),
    StructuredTool.from_function(
        coroutine=_llamar_cotizacion,
        name="agente_cotizacion",
        description=(
            "Cotiza una reparación correctiva del vehículo. Úsala para precios o fallas. "
            "NO la uses para agendar citas de mantenimiento preventivo."
        ),
        args_schema=ConsultaCliente,
        return_direct=True,
    ),
]

@dynamic_prompt
def _flujo_activo(request: ModelRequest) -> str:
    """Antepone "Flujo activo: <agente>" al prompt segun el ultimo agente del hilo."""
    activo = guardas.ultimo_agente(guardas.hilo_actual())
    if not activo:
        return prompts.ORQUESTADOR
    return f"Flujo activo: {activo}\n\n{prompts.ORQUESTADOR}"


_agente = None


def _construir():
    global _agente
    if _agente is None:
        _agente = create_agent(
            get_llm(),
            HERRAMIENTAS,
            system_prompt=prompts.ORQUESTADOR,
            middleware=[_flujo_activo],
            checkpointer=MEMORIA,
        )
    return _agente


def _seguimiento(mensaje, hilo_id):
    """El agente del flujo abierto que debe atender directo, o None si decide el orquestador."""
    activo = guardas.ultimo_agente(hilo_id)
    if not activo or not guardas.flujo_abierto(hilo_id):
        return None
    texto = mensaje.lower()
    if (activo == "citas" and "cotiz" in texto) or (activo == "cotizacion" and "cita" in texto):
        return None
    return activo


async def responder(mensaje, hilo_id):
    """Responde al cliente: en un flujo abierto llama directo a ese agente; si no, decide el orquestador."""
    guardas.iniciar_turno(hilo_id)
    if not comprobar_modelo():
        return guardas.MENSAJE_MODELO_APAGADO
    activo = _seguimiento(mensaje, hilo_id)
    if activo:
        guardas.fijar_agente(activo)
        agente = await (citas.preparar() if activo == "citas" else cotizacion.preparar())
    else:
        agente = _construir()
    config = {
        "configurable": {"thread_id": f"{hilo_id}:{activo}" if activo else hilo_id},
        "recursion_limit": 12 if activo else 8,
        "callbacks": [trazas.CALLBACK],
    }
    try:
        texto = await guardas.ejecutar(agente, config, mensaje)
    except APIConnectionError:
        return guardas.MENSAJE_MODELO_APAGADO
    except Exception as excepcion:
        guardas.registrar_error(excepcion)
        return guardas.MENSAJE_ERROR
    trazas.registrar_respuesta(texto)
    return texto
