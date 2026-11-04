"""Agente de citas: sus 5 herramientas MCP, su prompt y la memoria compartida."""
from langchain.agents import create_agent

from app.agentes import MEMORIA, guardas, mcp_clientes, prompts
from app.llm import get_llm

_agente = None


async def preparar():
    global _agente
    if _agente is None:
        herramientas = guardas.aplicar_guardas(await mcp_clientes.cargar("citas"))
        _agente = create_agent(
            get_llm(),
            herramientas,
            system_prompt=prompts.AGENTE_CITAS,
            checkpointer=MEMORIA,
        )
    return _agente


async def consultar(consulta, hilo_id):
    """Invoca el agente de citas en su hilo y devuelve su respuesta final."""
    agente = await preparar()
    resultado = await agente.ainvoke(
        {"messages": [("user", consulta)]},
        config={
            "configurable": {"thread_id": f"{hilo_id}:citas"},
            "recursion_limit": 12,
            "metadata": {"hilo_id": hilo_id},
            "tags": ["autonorte", "citas"],
            "run_name": "autonorte_citas",
        },
    )
    return guardas.texto_de(resultado)
