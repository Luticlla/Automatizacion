"""Trazas de las conversaciones: una linea JSON por evento en var/trazas.jsonl."""
import json
from datetime import datetime

from langchain_core.callbacks import BaseCallbackHandler

from app import config

RUTA_TRAZAS = config.RUTA_VAR / "trazas.jsonl"

HERRAMIENTAS_CITAS = {"validar_solicitud", "consultar_disponibilidad", "preparar_cita", "confirmar_cita"}
HERRAMIENTAS_COTIZACION = {"consultar_tarifario", "armar_cotizacion", "validar_politica_comercial", "programar_servicio"}


def _hilo():
    from app.agentes import guardas
    return guardas.hilo_actual()


def registrar(evento):
    """Escribe una linea JSON en var/trazas.jsonl y un resumen corto en consola."""
    registro = {"hora": datetime.now().isoformat(sep=" ", timespec="seconds"), "hilo_id": _hilo(), **evento}
    with open(RUTA_TRAZAS, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    print(f"[traza] {registro.get('hilo_id', '')} | {registro.get('agente', '')} | {registro.get('herramienta', '')} | {registro.get('codigo', '')}")


def registrar_respuesta(texto):
    """Anota el texto final que recibio el cliente."""
    registrar({
        "tipo": "respuesta",
        "agente": "orquestador",
        "herramienta": "respuesta",
        "argumentos": "",
        "codigo": "OK",
        "texto": texto,
    })


def _cuerpo(resultado):
    contenido = getattr(resultado, "content", None)
    if contenido is not None:
        return _cuerpo(contenido)
    if isinstance(resultado, list):
        for bloque in resultado:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                return bloque.get("text", "")
        return ""
    return resultado


def _codigo(resultado):
    cuerpo = _cuerpo(resultado)
    datos = None
    if isinstance(cuerpo, dict):
        datos = cuerpo
    elif isinstance(cuerpo, str):
        try:
            datos = json.loads(cuerpo)
        except ValueError:
            return "OK"
    if isinstance(datos, dict):
        return "OK" if datos.get("ok") else datos.get("codigo", "ERROR")
    return "OK"


def _resultado(resultado):
    """El diccionario del resultado JSON de una herramienta, si se puede leer."""
    cuerpo = _cuerpo(resultado)
    if isinstance(cuerpo, dict):
        return cuerpo
    if isinstance(cuerpo, str):
        try:
            datos = json.loads(cuerpo)
        except ValueError:
            return None
        if isinstance(datos, dict):
            return datos
    return None


def _texto_salida(resultado):
    """El texto final de un agente (no el JSON de una herramienta), si lo hay."""
    cuerpo = _cuerpo(resultado)
    if isinstance(cuerpo, str):
        try:
            json.loads(cuerpo)
        except ValueError:
            return cuerpo
    return ""


class Trazas(BaseCallbackHandler):
    """Callback que anota cada herramienta llamada, con su resultado y su agente."""

    def __init__(self):
        super().__init__()
        self._abiertas = {}
        self._saltadas = set()
        self._pila = []
        self.eventos = []

    def on_tool_start(self, serialized, input_str, run_id=None, parent_run_id=None, **kwargs):
        nombre = (serialized or {}).get("name", "")
        abierto = self._abiertas.get(parent_run_id)
        if abierto and abierto["herramienta"] == nombre:
            self._saltadas.add(run_id)
            return
        agente = "orquestador"
        if self._pila:
            agente = self._pila[-1][1]
        elif nombre in HERRAMIENTAS_CITAS:
            agente = "citas"
        elif nombre in HERRAMIENTAS_COTIZACION:
            agente = "cotizacion"
        if nombre == "agente_citas":
            self._pila.append((run_id, "citas"))
        elif nombre == "agente_cotizacion":
            self._pila.append((run_id, "cotizacion"))
        self._abiertas[run_id] = {"agente": agente, "herramienta": nombre, "argumentos": input_str}

    def on_tool_end(self, output, run_id=None, **kwargs):
        if run_id in self._saltadas:
            self._saltadas.discard(run_id)
            return
        datos = self._abiertas.pop(run_id, None)
        if not datos:
            return
        if self._pila and self._pila[-1][0] == run_id:
            self._pila.pop()
        evento = {"tipo": "herramienta", **datos, "codigo": _codigo(output)}
        resumen = _resultado(output)
        if resumen is not None:
            evento["resultado"] = resumen
        texto = _texto_salida(output)
        if texto:
            evento["texto"] = texto
        registrar(evento)
        self.eventos.append(evento)


CALLBACK = Trazas()
