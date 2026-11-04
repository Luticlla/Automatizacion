"""Servidor MCP de cotizaciones (stdio): expone las 5 herramientas de logica.py."""
import sys
import traceback

from mcp.server.fastmcp import FastMCP

from app import comun, db
from app.mcp_cotizaciones import logica

mcp = FastMCP("cotizaciones")


def _ejecutar(funcion):
    def llamada():
        with db.abrir_proceso2() as conn:
            return funcion(conn)

    try:
        return comun.con_reintento(llamada)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return comun.error(
            "ERROR_DE_SISTEMA", "Ocurrio un error inesperado.", "Deriva a una persona", clase="sistema"
        )


@mcp.tool()
def consultar_tarifario(descripcion: str) -> dict:
    """Busca en el tarifario por palabras clave de la falla o del servicio.
    Usala cuando el cliente describa una falla o pida una cotizacion.
    NO la uses para dar precios inventados ni para citas de mantenimiento preventivo."""
    return _ejecutar(lambda conn: logica.consultar_tarifario(conn, descripcion))


@mcp.tool()
def armar_cotizacion(codigos: list[str], vehiculo: str, placa: str = "") -> dict:
    """Arma la cotizacion con los precios del tarifario y calcula el total.
    Usala con los codigos que devolvio consultar_tarifario, el vehiculo y la placa opcional.
    NO la uses con codigos inventados: los precios y el total los calcula el codigo."""
    return _ejecutar(lambda conn: logica.armar_cotizacion(conn, codigos, vehiculo, placa))


@mcp.tool()
def validar_politica_comercial(id_cotizacion: str, descuento_solicitado_pct: float = 0) -> dict:
    """Valida el monto y el descuento contra la politica comercial y emite el testigo.
    Usala despues de armar_cotizacion y antes de programar_servicio.
    NO la uses para inventar descuentos ni para cambiar el total de la cotizacion."""
    return _ejecutar(lambda conn: logica.validar_politica_comercial(conn, id_cotizacion, descuento_solicitado_pct))


@mcp.tool()
def programar_servicio(testigo: str, decision: str = "aceptar") -> dict:
    """Consume el testigo y crea la orden de trabajo solo si el cliente confirma.
    Usala solo cuando el cliente confirme en su siguiente mensaje tras preguntarle.
    NO la uses cuando el cliente acepta la cotizacion: primero pide que confirme."""
    return _ejecutar(lambda conn: logica.programar_servicio(conn, testigo, decision))


@mcp.tool()
def derivar_a_humano(motivo: str, consulta_original: str, id_cotizacion: str = "") -> dict:
    """Encola el caso para un asesor con la cotizacion y los pasos previos.
    Usala cuando una regla lo indique o el cliente pida algo fuera de alcance.
    NO la uses si el caso se resuelve con las otras herramientas."""
    return _ejecutar(lambda conn: logica.derivar_a_humano(conn, motivo, consulta_original, id_cotizacion))


if __name__ == "__main__":
    mcp.run()
