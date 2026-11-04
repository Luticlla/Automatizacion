"""Demo de las cadenas LCEL explicitas: invoke, batch y astream (sin chat)."""
import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.lcel.cadenas import cadena_intencion, cadena_resumen_derivacion

MENSAJES = (
    "Quiero una cita de mantenimiento preventivo para mi placa A1B-234.",
    "Mi Toyota Hilux frena mal y hace ruido al frenar, cuanto cuesta?",
    "¿Quién ganó el partido de ayer?",
)

DERIVACIONES = (
    {
        "motivo": "SIN_KIT",
        "consulta_original": "Quiero cita de preventivo 20000 para mi placa A1B-234.",
        "datos_obtenidos": "El kit del servicio no tiene stock.",
        "pasos": "validar_solicitud -> consultar_disponibilidad",
    },
    {
        "motivo": "REQUIERE_APROBACION",
        "consulta_original": "Necesito cita para mi camioneta el 2026-10-23.",
        "datos_obtenidos": "La duracion estimada supera las 2 horas.",
        "pasos": "validar_solicitud -> consultar_disponibilidad",
    },
)


async def recorrer_stream():
    print("== cadena_intencion.astream ==")
    for mensaje in MENSAJES:
        print(f"{mensaje} -> ", end="", flush=True)
        async for trozo in cadena_intencion.astream({"mensaje": mensaje}):
            print(trozo, end="", flush=True)
        print()


def main():
    print("== cadena_intencion.invoke ==")
    for mensaje in MENSAJES:
        salida = cadena_intencion.invoke({"mensaje": mensaje})
        print(f"{mensaje} -> {salida}")

    print("== cadena_intencion.batch ==")
    salidas = cadena_intencion.batch([{"mensaje": mensaje} for mensaje in MENSAJES])
    for mensaje, salida in zip(MENSAJES, salidas):
        print(f"{mensaje} -> {salida}")

    asyncio.run(recorrer_stream())

    print("== cadena_resumen_derivacion.invoke ==")
    for datos in DERIVACIONES:
        print(cadena_resumen_derivacion.invoke(datos))


if __name__ == "__main__":
    main()
