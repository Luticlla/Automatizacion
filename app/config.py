"""Configuracion del proyecto: lee .env y expone rutas y la fecha de hoy."""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

MODEL_BACKEND = os.getenv("MODEL_BACKEND", "llamacpp")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "http://127.0.0.1:8080/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen")

RUTA_DATOS = BASE_DIR / "datos"
RUTA_VAR = BASE_DIR / "var"
RUTA_VAR.mkdir(exist_ok=True)


def hoy() -> date:
    """Devuelve HOY_FIJO como fecha si esta definido; si no, la fecha del sistema."""
    valor = os.getenv("HOY_FIJO", "").strip()
    if valor:
        return date.fromisoformat(valor)
    return date.today()
