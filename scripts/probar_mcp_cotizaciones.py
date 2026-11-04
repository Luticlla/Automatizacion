"""Prueba el servidor MCP de cotizaciones por stdio, sin modelo: lista herramientas y ejecuta 3 recorridos."""
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
    args=["-m", "app.mcp_cotizaciones.server"],
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
    db.reiniciar_proceso2()
    print("Base var/proceso2.db reiniciada para la prueba (datos/ no se toca).")

    async with stdio_client(PARAMETROS) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()

            listado = await sesion.list_tools()
            print(f"\nHerramientas ({len(listado.tools)}):")
            for herramienta in listado.tools:
                print(f"- {herramienta.name}:")
                for linea in (herramienta.description or "").splitlines():
                    print(f"    {linea}")

            print("\n=== Recorrido feliz: cotizacion aceptada (debe terminar en OT-0001) ===")
            await llamar(sesion, "consultar_tarifario", {"descripcion": "frena mal y hace ruido al frenar"})
            cotizacion = await llamar(sesion, "armar_cotizacion", {
                "codigos": ["FRE-01"],
                "vehiculo": "Toyota Corolla 2019",
                "placa": "T4M-891",
            })
            politica = await llamar(sesion, "validar_politica_comercial", {
                "id_cotizacion": cotizacion["id_cotizacion"],
            })
            orden = await llamar(sesion, "programar_servicio", {
                "testigo": politica["testigo"],
                "decision": "aceptar",
            })
            print(f"\nResultado del recorrido feliz: {orden.get('id_ot')}")

            print("\n=== Caso 2: monto alto, requiere aprobacion ===")
            await llamar(sesion, "consultar_tarifario", {
                "descripcion": "cambio de embrague y cambio de correa de distribucion",
            })
            alta = await llamar(sesion, "armar_cotizacion", {
                "codigos": ["EMB-01", "DIS-01"],
                "vehiculo": "Honda Civic 2020",
            })
            await llamar(sesion, "validar_politica_comercial", {"id_cotizacion": alta["id_cotizacion"]})

            print("\n=== Caso 3: servicio no encontrado ===")
            await llamar(sesion, "consultar_tarifario", {"descripcion": "aire acondicionado nuevo"})


if __name__ == "__main__":
    asyncio.run(main())
