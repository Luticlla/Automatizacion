"""Prueba el servidor MCP de citas por stdio, sin modelo: lista herramientas y ejecuta 4 recorridos."""
import asyncio
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app import db

PARAMETROS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "app.mcp_citas.server"],
    cwd=str(RAIZ),
)


async def llamar(sesion, nombre, argumentos):
    respuesta = await sesion.call_tool(nombre, argumentos)
    if respuesta.structuredContent is not None:
        datos = respuesta.structuredContent
    else:
        datos = json.loads(respuesta.content[0].text)
    print(f"\n-> {nombre}({json.dumps(argumentos, ensure_ascii=False)})")
    print(json.dumps(datos, ensure_ascii=False, indent=2))
    return datos


async def main():
    db.reiniciar_proceso1()
    print("Base var/proceso1.db reiniciada para la prueba (datos/ no se toca).")

    async with stdio_client(PARAMETROS) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()

            listado = await sesion.list_tools()
            print(f"\nHerramientas ({len(listado.tools)}):")
            for herramienta in listado.tools:
                print(f"- {herramienta.name}:")
                for linea in (herramienta.description or "").splitlines():
                    print(f"    {linea}")

            print("\n=== Recorrido feliz: cita nueva (debe terminar en CITA-0002) ===")
            validacion = await llamar(sesion, "validar_solicitud", {
                "solicitante": "Marco Ruiz Delgado",
                "telefono": "987654321",
                "placa": "A1B-234",
                "tipo_servicio": "preventivo_10000",
                "fecha_solicitada": "2026-10-21",
            })
            clave = validacion["clave"]
            await llamar(sesion, "consultar_disponibilidad", {"clave": clave})
            preparacion = await llamar(sesion, "preparar_cita", {"clave": clave})
            confirmacion = await llamar(sesion, "confirmar_cita", {"testigo": preparacion["testigo"]})
            print(f"\nResultado del recorrido feliz: {confirmacion.get('id_cita')}")

            print("\n=== Error 1: contrato con cuatro datos invalidos ===")
            await llamar(sesion, "validar_solicitud", {
                "solicitante": "Juan Perez",
                "telefono": "12345",
                "placa": "ABC123",
                "tipo_servicio": "preventivo_15000",
                "fecha_solicitada": "2026-10-01",
            })

            print("\n=== Error 2: fecha sin cupo (alternativas) ===")
            validacion = await llamar(sesion, "validar_solicitud", {
                "solicitante": "Ana Torres Rios",
                "telefono": "912345678",
                "placa": "B2C-345",
                "tipo_servicio": "preventivo_10000",
                "fecha_solicitada": "2026-10-22",
            })
            await llamar(sesion, "consultar_disponibilidad", {"clave": validacion["clave"]})

            print("\n=== Error 3: testigo invalido ===")
            await llamar(sesion, "confirmar_cita", {"testigo": "T-00000000"})


if __name__ == "__main__":
    asyncio.run(main())
