"""Verifica las variables de LangSmith y ejecuta una cadena de prueba."""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import config  # noqa: F401  (carga .env)
from app.lcel.cadenas import cadena_intencion

VARIABLES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
)
MARCADOR = "pon_tu_clave_aqui"


def revisar_variables():
    """Comprueba que las variables existan y no sean el marcador de ejemplo."""
    todo_ok = True
    for nombre in VARIABLES:
        valor = os.getenv(nombre, "").strip()
        if not valor or valor == MARCADOR:
            print(f"{nombre}: FALTA")
            todo_ok = False
        elif nombre == "LANGSMITH_API_KEY":
            print(f"{nombre}: definida")
        else:
            print(f"{nombre}: {valor}")
    return todo_ok


def main():
    if not revisar_variables():
        print("LangSmith no esta configurado; no se ejecuta la prueba.")
        return 1
    salida = cadena_intencion.invoke(
        {"mensaje": "Quiero una cita de mantenimiento preventivo."},
        config={
            "run_name": "verificacion_langsmith",
            "tags": ["autonorte", "verificacion"],
            "metadata": {"origen": "scripts/verificar_langsmith.py"},
        },
    )
    print(f"Ejecucion de prueba: {salida}")
    from langsmith import Client

    cliente = Client()
    cliente.flush()
    print(f"Trazas enviadas al proyecto {os.getenv('LANGSMITH_PROJECT')}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
