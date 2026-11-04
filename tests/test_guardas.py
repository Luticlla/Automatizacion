"""Pruebas unitarias de las guardas de los agentes, sin modelo."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.tools import StructuredTool

from app.agentes import guardas


class ServidorFalso:
    def __init__(self):
        self.llamadas = []

    async def preparar_cita(self, clave: str = "") -> dict:
        self.llamadas.append("preparar_cita")
        return {"ok": True, "resumen": {"placa": "A1B-234"}, "testigo": "T-FALSO01"}

    async def confirmar_cita(self, testigo: str) -> dict:
        self.llamadas.append("confirmar_cita")
        return {"ok": True, "id_cita": "CITA-0099"}


def _herramientas(servidor):
    preparar = StructuredTool.from_function(
        coroutine=servidor.preparar_cita, name="preparar_cita", description="Emite un testigo."
    )
    confirmar = StructuredTool.from_function(
        coroutine=servidor.confirmar_cita, name="confirmar_cita", description="Consume un testigo."
    )
    return guardas.aplicar_guardas([preparar, confirmar])


def test_testigo_emitido_y_usado_en_el_mismo_turno():
    servidor = ServidorFalso()
    preparar, confirmar = _herramientas(servidor)

    async def caso():
        guardas.iniciar_turno("hilo-prueba")
        await preparar.ainvoke({})
        emitidos = set(guardas.turno_actual())
        respuesta = await confirmar.ainvoke({"testigo": "T-FALSO01"})
        return emitidos, respuesta

    emitidos, respuesta = asyncio.run(caso())
    assert "T-FALSO01" in emitidos
    assert json.loads(respuesta)["codigo"] == "ESPERAR_CONFIRMACION"
    assert servidor.llamadas == ["preparar_cita"]


def test_testigo_de_un_turno_anterior_si_confirma():
    servidor = ServidorFalso()
    preparar, confirmar = _herramientas(servidor)

    async def caso():
        guardas.iniciar_turno("hilo-prueba")
        await preparar.ainvoke({})
        guardas.iniciar_turno("hilo-prueba")
        return await confirmar.ainvoke({"testigo": "T-FALSO01"})

    respuesta = asyncio.run(caso())
    assert respuesta["ok"] is True
    assert respuesta["id_cita"] == "CITA-0099"
    assert servidor.llamadas == ["preparar_cita", "confirmar_cita"]


class ServidorCotizacionFalso:
    def __init__(self):
        self.llamadas = []

    async def validar_politica_comercial(self, id_cotizacion: str = "") -> dict:
        self.llamadas.append("validar_politica_comercial")
        return {"ok": True, "id_cotizacion": id_cotizacion, "testigo": "T-FALSO02"}

    async def programar_servicio(self, testigo: str, decision: str = "aceptar") -> dict:
        self.llamadas.append("programar_servicio")
        return {"ok": True, "id_cotizacion": "COT-0001", "id_ot": "OT-0001"}


def _herramientas_cotizacion(servidor):
    validar = StructuredTool.from_function(
        coroutine=servidor.validar_politica_comercial,
        name="validar_politica_comercial",
        description="Emite un testigo.",
    )
    programar = StructuredTool.from_function(
        coroutine=servidor.programar_servicio, name="programar_servicio", description="Consume un testigo."
    )
    return guardas.aplicar_guardas([validar, programar])


def test_afirmar_confirmado_sin_pregunta_no_autoriza_programar():
    servidor = ServidorCotizacionFalso()
    validar, programar = _herramientas_cotizacion(servidor)

    async def caso():
        guardas.iniciar_turno("hilo-cotizacion")
        await validar.ainvoke({})
        guardas.anotar_respuesta("Su cotización fue confirmada.")
        guardas.iniciar_turno("hilo-cotizacion")
        bloqueado = await programar.ainvoke({"testigo": "T-FALSO02"})
        guardas.anotar_respuesta("¿Confirmas que programe el servicio?")
        guardas.iniciar_turno("hilo-cotizacion")
        permitido = await programar.ainvoke({"testigo": "T-FALSO02"})
        return bloqueado, permitido

    bloqueado, permitido = asyncio.run(caso())
    assert json.loads(bloqueado)["codigo"] == "ESPERAR_CONFIRMACION"
    assert permitido["ok"] is True
    assert servidor.llamadas == ["validar_politica_comercial", "programar_servicio"]


def test_pregunta_de_confirmacion_asegurada_si_el_modelo_no_la_hizo():
    async def caso():
        guardas.iniciar_turno("hilo-pregunta")
        guardas.PEDIR_CONFIRMACION["hilo-pregunta"] = True
        sin_pregunta = guardas.asegurar_pregunta("Su cotización es de S/ 270.00.")
        guardas.iniciar_turno("hilo-pregunta")
        guardas.PEDIR_CONFIRMACION["hilo-pregunta"] = True
        con_pregunta = guardas.asegurar_pregunta("¿Confirmas que programe el servicio?")
        return sin_pregunta, con_pregunta

    sin_pregunta, con_pregunta = asyncio.run(caso())
    assert "¿Confirmas que programe el servicio?" in sin_pregunta
    assert con_pregunta == "¿Confirmas que programe el servicio?"


def test_ultimo_agente_por_hilo():
    guardas.iniciar_turno("hilo-agente-a")
    guardas.fijar_agente("citas")
    guardas.iniciar_turno("hilo-agente-b")
    guardas.fijar_agente("cotizacion")
    assert guardas.ultimo_agente("hilo-agente-a") == "citas"
    assert guardas.ultimo_agente("hilo-agente-b") == "cotizacion"
    assert guardas.ultimo_agente("hilo-sin-agente") is None


class ServidorDerivarFalso:
    async def derivar_a_humano(self, motivo: str = "", consulta_original: str = "") -> dict:
        return {"ok": True, "id": 1}


def test_seguimiento_con_flujo_abierto_llama_directo():
    from app.agentes import orquestador

    guardas.iniciar_turno("hilo-abierto")
    guardas.fijar_agente("citas")
    assert guardas.flujo_abierto("hilo-abierto") is True
    assert orquestador._seguimiento("Sí, confirmo.", "hilo-abierto") == "citas"


def test_flujo_cerrado_vuelve_al_orquestador():
    from app.agentes import orquestador

    async def caso():
        servidor = ServidorCotizacionFalso()
        validar, programar = _herramientas_cotizacion(servidor)
        guardas.iniciar_turno("hilo-cerrado")
        guardas.fijar_agente("cotizacion")
        await validar.ainvoke({})
        guardas.anotar_respuesta("¿Confirmas que programe el servicio?")
        guardas.iniciar_turno("hilo-cerrado")
        resultado = await programar.ainvoke({"testigo": "T-FALSO02"})
        return resultado, guardas.flujo_abierto("hilo-cerrado")

    resultado, abierto = asyncio.run(caso())
    assert resultado["ok"] is True
    assert abierto is False
    assert orquestador._seguimiento("Sí, confirmo.", "hilo-cerrado") is None


def test_derivar_a_humano_ok_tambien_cierra_el_flujo():
    servidor = ServidorDerivarFalso()
    derivar = StructuredTool.from_function(
        coroutine=servidor.derivar_a_humano, name="derivar_a_humano", description="Deriva."
    )
    (envuelta,) = guardas.aplicar_guardas([derivar])

    async def caso():
        guardas.iniciar_turno("hilo-derivar")
        guardas.fijar_agente("citas")
        resultado = await envuelta.ainvoke({"motivo": "FUERA_DE_ALCANCE", "consulta_original": "x"})
        return resultado, guardas.flujo_abierto("hilo-derivar")

    resultado, abierto = asyncio.run(caso())
    assert resultado["ok"] is True
    assert abierto is False


def test_cambio_de_tema_decide_el_orquestador():
    from app.agentes import orquestador

    guardas.iniciar_turno("hilo-cambio")
    guardas.fijar_agente("citas")
    assert orquestador._seguimiento("Mejor quiero una cotizacion, deja la cita.", "hilo-cambio") is None
    guardas.fijar_agente("cotizacion")
    assert orquestador._seguimiento("¿Y una cita para el mantenimiento?", "hilo-cambio") is None


def test_modelo_apagado_responde_sin_traceback(monkeypatch):
    from app import config
    from app.agentes import orquestador

    monkeypatch.setattr(config, "MODEL_BASE_URL", "http://127.0.0.1:9/v1")
    respuesta = asyncio.run(orquestador.responder("Hola", "hilo-apagado"))
    assert respuesta == guardas.MENSAJE_MODELO_APAGADO
