"""API FastAPI: la pagina del chat, el panel de solo lectura y la salud del servicio."""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import config, db
from app.agentes import orquestador
from app.llm import comprobar_modelo

RUTA_WEB = Path(__file__).resolve().parents[1] / "web"
RUTA_TEXTOS = config.RUTA_DATOS / "ui" / "textos_chat.json"

CANDADO_MODELO = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    """Prepara las bases y avisa si el modelo no esta encendido."""
    db.iniciar_si_no_existen()
    if not comprobar_modelo():
        print(
            f"ADVERTENCIA: el modelo no responde en {config.MODEL_BASE_URL}; "
            "el chat devolverá el mensaje de modelo apagado."
        )
    yield


app = FastAPI(title="Asistente de Autonorte", lifespan=lifespan)


class PedidoChat(BaseModel):
    mensaje: str
    hilo_id: str


@app.get("/")
def pagina():
    """Entrega la pagina del chat."""
    return FileResponse(RUTA_WEB / "index.html")


@app.get("/api/textos")
def textos():
    """Contenido de datos/ui/textos_chat.json."""
    return json.loads(RUTA_TEXTOS.read_text(encoding="utf-8"))


@app.get("/api/salud")
def salud():
    """Estado de la API y del modelo local."""
    return {"api": True, "modelo": comprobar_modelo()}


@app.post("/api/chat")
async def chat(pedido: PedidoChat):
    """Atiende un mensaje del cliente; una peticion al modelo a la vez."""
    mensaje = pedido.mensaje.strip()
    if not mensaje:
        raise HTTPException(status_code=422, detail="El mensaje no puede estar vacío.")
    if len(mensaje) > 1000:
        raise HTTPException(status_code=422, detail="El mensaje no puede superar los 1000 caracteres.")
    async with CANDADO_MODELO:
        respuesta = await orquestador.responder(mensaje, pedido.hilo_id)
    return {"respuesta": respuesta, "hilo_id": pedido.hilo_id}


@app.get("/api/panel")
def panel():
    """Panel de solo lectura: citas, tareas pendientes, cotizaciones y contadores."""
    with db.abrir_proceso1() as con1:
        citas = [
            dict(fila)
            for fila in con1.execute(
                "SELECT id_cita AS id, fecha, hora, placa, tipo_servicio, solicitante, estado"
                " FROM citas ORDER BY id_cita DESC"
            )
        ]
        tareas = [
            dict(fila)
            for fila in con1.execute(
                "SELECT id, proceso, motivo, fecha_hora, estado FROM cola_excepciones"
            )
        ]
        citas_confirmadas = con1.execute(
            "SELECT COUNT(*) AS total FROM citas WHERE estado = 'confirmada'"
        ).fetchone()["total"]
        pendientes = con1.execute(
            "SELECT COUNT(*) AS total FROM cola_excepciones WHERE estado = 'pendiente'"
        ).fetchone()["total"]
    with db.abrir_proceso2() as con2:
        cotizaciones = [
            dict(fila)
            for fila in con2.execute(
                "SELECT c.id_cotizacion AS id, c.vehiculo, c.total, c.estado, o.id_ot"
                " FROM cotizaciones c LEFT JOIN ordenes_trabajo o ON o.id_cotizacion = c.id_cotizacion"
                " ORDER BY c.id_cotizacion DESC"
            )
        ]
        tareas += [
            dict(fila)
            for fila in con2.execute(
                "SELECT id, proceso, motivo, fecha_hora, estado FROM cola_excepciones"
            )
        ]
        pendientes += con2.execute(
            "SELECT COUNT(*) AS total FROM cola_excepciones WHERE estado = 'pendiente'"
        ).fetchone()["total"]
        ordenes = con2.execute("SELECT COUNT(*) AS total FROM ordenes_trabajo").fetchone()["total"]
    tareas.sort(key=lambda tarea: tarea["fecha_hora"], reverse=True)
    return {
        "citas": citas,
        "tareas": tareas,
        "cotizaciones": cotizaciones,
        "contadores": {
            "citas_confirmadas": citas_confirmadas,
            "tareas_pendientes": pendientes,
            "ordenes_trabajo": ordenes,
        },
    }
