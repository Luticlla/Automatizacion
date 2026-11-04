"""Demo de HITL: pausa con interrupt() y reanuda con Command(resume=...)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from langgraph.types import Command

from app.lcel.hitl_demo import construir_grafo

RUTA_GRAFOS = RAIZ / "docs" / "grafos"


def guardar_diagrama(grafo):
    RUTA_GRAFOS.mkdir(parents=True, exist_ok=True)
    (RUTA_GRAFOS / "hitl.mmd").write_text(grafo.get_graph().draw_mermaid(), encoding="utf-8")


def ejecutar_caso(grafo, thread_id, aprobado):
    config = {"configurable": {"thread_id": thread_id}}
    pausa = grafo.invoke({"total": 2500}, config=config)
    interrupcion = pausa["__interrupt__"][0]
    print(f"== Caso {thread_id}: grafo en pausa ==")
    print(f"Payload del interrupt: {interrupcion.value}")
    final = grafo.invoke(Command(resume={"aprobado": aprobado}), config=config)
    print(f"Decision registrada: {final.get('decision')}")
    print(f"Estado final: {final}")
    print()


def main():
    grafo = construir_grafo()
    guardar_diagrama(grafo)
    ejecutar_caso(grafo, "hitl-aprueba", True)
    ejecutar_caso(grafo, "hitl-rechaza", False)


if __name__ == "__main__":
    main()
