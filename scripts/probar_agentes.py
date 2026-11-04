"""Conversaciones de prueba de los agentes, con el modelo encendido (especificacion 03)."""
import asyncio
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.agentes import orquestador, trazas

CONVERSACIONES = (
    ("hola-03", ("Hola, buenas tardes",)),
    ("cita-03", (
        "Quiero cita de preventivo 10000 para mi placa A1B-234 el 2026-10-21. Soy Marco Ruiz Delgado, telefono 987654321.",
        "Sí, confirmo.",
    )),
    ("cotizacion-03", ("Mi Toyota Hilux frena mal y hace ruido al frenar.",)),
    ("fuera-03", ("¿Quién ganó el partido de ayer?",)),
)


def lineas_trazas():
    if not trazas.RUTA_TRAZAS.exists():
        return []
    with open(trazas.RUTA_TRAZAS, encoding="utf-8") as archivo:
        return archivo.readlines()


def eventos_desde(inicio):
    eventos = []
    for linea in lineas_trazas()[inicio:]:
        try:
            eventos.append(json.loads(linea))
        except ValueError:
            continue
    return eventos


def mostrar_herramientas(eventos):
    llamadas = [evento for evento in eventos if evento.get("tipo") == "herramienta"]
    if not llamadas:
        print("    herramientas: ninguna")
        return
    for evento in llamadas:
        print(f"    herramienta: {evento['agente']} | {evento['herramienta']} | {evento['codigo']}")


async def main():
    for hilo, mensajes in CONVERSACIONES:
        for mensaje in mensajes:
            corte = len(lineas_trazas())
            print(f"\n[{hilo}] Cliente: {mensaje}")
            respuesta = await orquestador.responder(mensaje, hilo)
            print(f"[{hilo}] Asistente: {respuesta}")
            mostrar_herramientas(eventos_desde(corte))


if __name__ == "__main__":
    asyncio.run(main())
