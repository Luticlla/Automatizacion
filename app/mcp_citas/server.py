"""Servidor MCP de citas (stdio): expone las 5 herramientas de logica.py."""
import sys
import traceback

from mcp.server.fastmcp import FastMCP

from app import comun, db
from app.mcp_citas import logica

mcp = FastMCP("citas")


def _ejecutar(funcion):
    def llamada():
        with db.abrir_proceso1() as conn:
            return funcion(conn)

    try:
        return comun.con_reintento(llamada)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return comun.error(
            "ERROR_DE_SISTEMA", "Ocurrio un error inesperado.", "Deriva a una persona", clase="sistema"
        )


@mcp.tool()
def validar_solicitud(
    solicitante: str = "",
    telefono: str = "",
    placa: str = "",
    tipo_servicio: str = "",
    fecha_solicitada: str = "",
    descripcion: str = "",
) -> dict:
    """Valida los 5 datos del cliente y guarda la solicitud con su clave.
    Usala cuando ya tengas solicitante, telefono, placa, tipo_servicio y fecha_solicitada.
    NO la uses para cancelar ni reprogramar citas, ni con datos incompletos."""
    return _ejecutar(lambda conn: logica.validar_solicitud(
        conn, solicitante, telefono, placa, tipo_servicio, fecha_solicitada, descripcion
    ))


@mcp.tool()
def consultar_disponibilidad(clave: str) -> dict:
    """Consulta fecha de agenda, kit, cupo y duracion para una clave validada.
    Usala despues de validar_solicitud y antes de preparar_cita.
    NO la uses sin clave: tampoco reserva nada, solo informa."""
    return _ejecutar(lambda conn: logica.consultar_disponibilidad(conn, clave))


@mcp.tool()
def preparar_cita(clave: str) -> dict:
    """Verifica otra vez todo y emite el testigo de un solo uso para confirmar.
    Usala cuando el cliente quiera reservar la hora ofrecida.
    NO registra nada: la cita solo queda con confirmar_cita y el si del cliente."""
    return _ejecutar(lambda conn: logica.preparar_cita(conn, clave))


@mcp.tool()
def confirmar_cita(testigo: str) -> dict:
    """Registra la cita consumiendo el testigo que emitio preparar_cita.
    Usala solo despues de que el cliente confirme en un mensaje nuevo.
    NO la uses con un testigo de la misma conversacion en que se emitio."""
    return _ejecutar(lambda conn: logica.confirmar_cita(conn, testigo))


@mcp.tool()
def derivar_a_humano(motivo: str, consulta_original: str, clave: str = "") -> dict:
    """Encola el caso para que un asesor lo revise.
    Usala cuando una regla lo indique o el cliente pida cancelar, reprogramar u otra consulta.
    NO la uses si el caso se resuelve con las otras herramientas."""
    return _ejecutar(lambda conn: logica.derivar_a_humano(conn, motivo, consulta_original, clave))


if __name__ == "__main__":
    mcp.run()
