"""Demo del grafo determinista del proceso 1 y exportacion del diagrama."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from langgraph.types import Command

from app import db
from app.grafo_proceso1 import construir_grafo

RUTA_GRAFOS = RAIZ / "docs" / "grafos"


def guardar_diagrama(grafo):
    """Guarda el Mermaid y, si se puede, el PNG del grafo."""
    RUTA_GRAFOS.mkdir(parents=True, exist_ok=True)
    ruta_mmd = RUTA_GRAFOS / "proceso1.mmd"
    ruta_mmd.write_text(grafo.get_graph().draw_mermaid(), encoding="utf-8")
    print(f"Escrito {ruta_mmd.relative_to(RAIZ)}")
    try:
        png = grafo.get_graph().draw_mermaid_png(max_retries=1, retry_delay=0)
    except Exception as excepcion:
        print(f"PNG no disponible: {type(excepcion).__name__}: {excepcion}")
        return
    ruta_png = RUTA_GRAFOS / "proceso1.png"
    ruta_png.write_bytes(png)
    print(f"Escrito {ruta_png.relative_to(RAIZ)}")


def ejecutar_caso(grafo, nombre, hilo, solicitud, respuestas):
    """Invoca el grafo, muestra cada pausa y reanuda con las respuestas dadas."""
    print(f"\n== {nombre} ==")
    config = {"configurable": {"thread_id": hilo}}
    estado = grafo.invoke({"solicitud": solicitud}, config=config)
    pendientes = list(respuestas)
    while estado.get("__interrupt__"):
        pausa = estado["__interrupt__"][0].value
        print(f"Pausa {pausa.get('nodo')}: {pausa.get('pregunta')}")
        if not pendientes:
            raise SystemExit(f"Falta una respuesta para la pausa {pausa.get('nodo')}.")
        respuesta = pendientes.pop(0)
        print(f"Reanudar con: {respuesta}")
        estado = grafo.invoke(Command(resume=respuesta), config=config)
    print(f"Resultado: {estado.get('resultado')}")


def main():
    db.reiniciar_proceso1()
    grafo = construir_grafo()
    guardar_diagrama(grafo)

    ejecutar_caso(
        grafo,
        "Cita nueva",
        "demo-cita-nueva",
        {
            "solicitante": "Marco Ruiz Delgado",
            "telefono": "987654321",
            "placa": "A1B-234",
            "tipo_servicio": "preventivo_10000",
            "fecha_solicitada": "2026-10-21",
            "descripcion": "",
        },
        [],
    )
    ejecutar_caso(
        grafo,
        "Datos invalidos",
        "demo-datos-invalidos",
        {
            "solicitante": "Juan Perez",
            "telefono": "12345",
            "placa": "ABC123",
            "tipo_servicio": "preventivo_15000",
            "fecha_solicitada": "2026-10-01",
            "descripcion": "",
        },
        [{"corregido": True}],
    )
    ejecutar_caso(
        grafo,
        "Posible correctivo",
        "demo-posible-correctivo",
        {
            "solicitante": "Elena Rojas Paz",
            "telefono": "945678901",
            "placa": "E5F-678",
            "tipo_servicio": "preventivo_10000",
            "fecha_solicitada": "2026-10-23",
            "descripcion": "suena raro al frenar",
        },
        [{"decision": "correctivo"}],
    )
    ejecutar_caso(
        grafo,
        "Sin kit",
        "demo-sin-kit",
        {
            "solicitante": "Luis Pardo Soto",
            "telefono": "923456789",
            "placa": "C3D-456",
            "tipo_servicio": "preventivo_5000",
            "fecha_solicitada": "2026-10-21",
            "descripcion": "",
        },
        [{"decision": "gestionado"}],
    )
    ejecutar_caso(
        grafo,
        "Duracion mayor a 2 horas",
        "demo-duracion-larga",
        {
            "solicitante": "Rosa Diaz Luna",
            "telefono": "934567890",
            "placa": "D4E-567",
            "tipo_servicio": "preventivo_20000",
            "fecha_solicitada": "2026-10-21",
            "descripcion": "",
        },
        [{"aprobado": True}],
    )


if __name__ == "__main__":
    main()
