"""Agente de cotizacion: sus 5 herramientas MCP, su prompt y la memoria compartida."""
from langchain.agents import create_agent

from app.agentes import MEMORIA, guardas, mcp_clientes, prompts
from app.llm import get_llm

_agente = None


async def preparar():
    global _agente
    if _agente is None:
        herramientas = guardas.aplicar_guardas(await mcp_clientes.cargar("cotizaciones"))
        _agente = create_agent(
            get_llm(),
            herramientas,
            system_prompt=prompts.AGENTE_COTIZACION,
            checkpointer=MEMORIA,
        )
    return _agente


async def consultar(consulta, hilo_id):
    """Invoca el agente de cotizacion en su hilo y devuelve su respuesta final."""
    agente = await preparar()
    resultado = await agente.ainvoke(
        {"messages": [("user", consulta)]},
        config={"configurable": {"thread_id": f"{hilo_id}:cotizacion"}, "recursion_limit": 12},
    )
    return guardas.texto_de(resultado)
