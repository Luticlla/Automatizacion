"""Exporta los grafos de LangGraph a Mermaid y, si se puede, a PNG."""
import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.agentes import citas, cotizacion, orquestador
from app.lcel import hitl_demo

RUTA_GRAFOS = RAIZ / "docs" / "grafos"


def exportar(nombre, grafo):
    """Guarda el Mermaid y prueba el PNG; si no hay internet, deja solo el .mmd."""
    ruta_mmd = RUTA_GRAFOS / f"{nombre}.mmd"
    ruta_mmd.write_text(grafo.get_graph().draw_mermaid(), encoding="utf-8")
    print(f"Escrito {ruta_mmd.relative_to(RAIZ)}")
    try:
        png = grafo.get_graph().draw_mermaid_png(max_retries=1, retry_delay=0)
    except Exception as excepcion:
        print(f"PNG no disponible para {nombre}: {type(excepcion).__name__}: {excepcion}")
        return
    ruta_png = RUTA_GRAFOS / f"{nombre}.png"
    ruta_png.write_bytes(png)
    print(f"Escrito {ruta_png.relative_to(RAIZ)}")


async def main():
    RUTA_GRAFOS.mkdir(parents=True, exist_ok=True)
    grafos = {
        "orquestador": orquestador._construir(),
        "citas": await citas.preparar(),
        "cotizacion": await cotizacion.preparar(),
        "hitl": hitl_demo.construir_grafo(),
    }
    for nombre, grafo in grafos.items():
        exportar(nombre, grafo)


if __name__ == "__main__":
    asyncio.run(main())
