"""Acceso al modelo local y comprobacion de que el servidor responde."""
import httpx
from langchain_openai import ChatOpenAI

from app import config


def get_llm():
    """Devuelve el ChatOpenAI del modelo local; la nube queda bloqueada."""
    if config.MODEL_BACKEND != "llamacpp":
        raise RuntimeError(
            "MODEL_BACKEND distinto de llamacpp: este proyecto solo llama al modelo local. "
            "La nube requiere aprobacion expresa del equipo."
        )
    return ChatOpenAI(
        base_url=config.MODEL_BASE_URL,
        api_key="sin-clave",
        model=config.MODEL_NAME,
        temperature=0,
        timeout=120,
        max_retries=1,
    )


def comprobar_modelo():
    """Verdadero si el servidor del modelo responde a GET /models."""
    try:
        respuesta = httpx.get(f"{config.MODEL_BASE_URL}/models", timeout=2)
    except httpx.HTTPError:
        return False
    return respuesta.status_code == 200
