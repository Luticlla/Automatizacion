"""Clientes MCP stdio (uno por servidor): cada agente carga solo sus herramientas."""
import os
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

RAIZ = Path(__file__).resolve().parent.parent.parent


def _conexion(modulo):
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", modulo],
        "cwd": str(RAIZ),
        "env": dict(os.environ),
    }


CONEXIONES = {
    "citas": _conexion("app.mcp_citas.server"),
    "cotizaciones": _conexion("app.mcp_cotizaciones.server"),
}

_cache = {}


async def cargar(servidor):
    """Herramientas de un servidor ('citas' o 'cotizaciones'), una vez por proceso."""
    if servidor not in _cache:
        cliente = MultiServerMCPClient({servidor: CONEXIONES[servidor]})
        _cache[servidor] = await cliente.get_tools(server_name=servidor)
    return _cache[servidor]
