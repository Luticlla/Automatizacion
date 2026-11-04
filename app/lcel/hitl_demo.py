"""Demo de HITL con interrupt() de LangGraph, sin conectarla al chat."""
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

UMBRAL_APROBACION = 2000


class EstadoAprobacion(TypedDict, total=False):
    total: float
    aprobado: bool
    decision: str


def evaluar_monto(estado: EstadoAprobacion) -> EstadoAprobacion:
    """Deja el monto en el estado para que la arista condicional decida."""
    return {"total": estado["total"]}


def requiere_aprobacion(estado: EstadoAprobacion) -> str:
    """Manda al jefe de taller si el total supera el umbral; si no, registra directo."""
    if estado["total"] > UMBRAL_APROBACION:
        return "aprobacion_jefe"
    return "registrar_decision"


def aprobacion_jefe(estado: EstadoAprobacion) -> EstadoAprobacion:
    """Pausa el grafo con interrupt() y espera la decision del jefe de taller."""
    respuesta = interrupt({
        "pregunta": "El total supera S/ 2000. ¿Aprueba el jefe de taller?",
        "total": estado["total"],
        "umbral": UMBRAL_APROBACION,
    })
    return {"aprobado": bool(respuesta.get("aprobado"))}


def registrar_decision(estado: EstadoAprobacion) -> EstadoAprobacion:
    """Cierra el caso con la decision final."""
    if estado["total"] > UMBRAL_APROBACION and not estado.get("aprobado"):
        return {"decision": "rechazada"}
    return {"decision": "aprobada"}


def construir_grafo():
    """Compila el grafo HITL con memoria en proceso para poder reanudarlo."""
    constructor = StateGraph(EstadoAprobacion)
    constructor.add_node("evaluar_monto", evaluar_monto)
    constructor.add_node("aprobacion_jefe", aprobacion_jefe)
    constructor.add_node("registrar_decision", registrar_decision)
    constructor.add_edge(START, "evaluar_monto")
    constructor.add_conditional_edges(
        "evaluar_monto",
        requiere_aprobacion,
        {
            "aprobacion_jefe": "aprobacion_jefe",
            "registrar_decision": "registrar_decision",
        },
    )
    constructor.add_edge("aprobacion_jefe", "registrar_decision")
    constructor.add_edge("registrar_decision", END)
    return constructor.compile(checkpointer=InMemorySaver())
