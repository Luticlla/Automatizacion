# Especificación 04 — API y chat web en localhost

Requisito: la especificación 03 está terminada (`responder(mensaje, hilo_id)` funciona).
Fuente de los textos de la interfaz: `datos/ui/textos_chat.json`. No escribas esos textos dentro del HTML; léelos de ese archivo.

## API (`app/api/main.py`, FastAPI)

Se ejecuta con `uvicorn app.api.main:app --port 8000` y escucha solo en `127.0.0.1`.

| Ruta | Método | Entrada | Salida |
| --- | --- | --- | --- |
| `/` | GET | | la página `app/web/index.html` |
| `/api/textos` | GET | | el contenido de `datos/ui/textos_chat.json` |
| `/api/chat` | POST | `{"mensaje": str, "hilo_id": str}` | `{"respuesta": str, "hilo_id": str}` |
| `/api/panel` | GET | | `{"citas": [...], "tareas": [...], "cotizaciones": [...], "contadores": {...}}` |
| `/api/salud` | GET | | `{"api": true, "modelo": true/false}` |

- Al arrancar (lifespan): `iniciar_si_no_existen()` de `db.py`, abrir las sesiones MCP si la especificación 03 las usa, y comprobar el modelo; si está apagado, escribir una advertencia en consola (la API arranca igual).
- `/api/chat`: valida que `mensaje` no esté vacío y tenga como máximo 1000 caracteres (si no, error 422 con mensaje en español); llama a `responder`. Las peticiones al modelo se atienden **una a la vez** (un `asyncio.Lock`), porque hay un solo modelo local. Nunca devuelve un traceback: ante un error inesperado responde 200 con un texto amable (la guarda 5 de la especificación 03 ya lo hace).
- `/api/panel` solo lee SQLite; no usa el modelo:
  - `citas`: de `proceso1.db`, tabla `citas` (id, fecha, hora, placa, tipo de servicio, solicitante, estado), más recientes primero.
  - `tareas`: unión de `cola_excepciones` de ambas bases (id, proceso, motivo, fecha y hora, estado), más recientes primero.
  - `cotizaciones`: de `proceso2.db`, con su orden de trabajo si existe (id de cotización, vehículo, total, estado, id de OT).
  - `contadores`: `citas_confirmadas`, `tareas_pendientes`, `ordenes_trabajo`.
- Sin autenticación, sin CORS abierto (la página se sirve desde la misma API).

## Página (`app/web/index.html`)

Un solo archivo con HTML, CSS y JavaScript sin dependencias (sin Node, sin frameworks, sin CDN: debe funcionar sin internet). Estilo sobrio: fondo claro, un solo color de acento, tipografía del sistema, esquinas redondeadas suaves. Pensada para escritorio (no hace falta versión móvil).

Diseño de dos columnas, como la captura de la sesión S06:

**Columna izquierda: el chat** (ocupa dos tercios del ancho)
- Encabezado con `titulo` y `subtitulo`.
- Zona de mensajes con scroll. Al abrir muestra el `saludo` como primera burbuja del asistente.
- Debajo del saludo, las 3 `sugerencias` como botones tipo "chip". Al pulsar uno se envía su texto como mensaje del cliente. Los chips desaparecen cuando se envía el primer mensaje.
- Burbujas: las del cliente a la derecha con color de acento, las del asistente a la izquierda en gris claro. Texto plano con saltos de línea respetados (`white-space: pre-wrap`); insertar siempre con `textContent`, nunca como HTML.
- Mientras espera la respuesta: una burbuja del asistente con el texto `pensando` y puntos animados; la caja de texto y el botón de enviar quedan deshabilitados.
- Caja de texto con `placeholder` y botón de enviar; Enter envía, Mayús+Enter agrega una línea.
- Pie con el texto `pie`.
- Botón pequeño "Nueva conversación" que genera un `hilo_id` nuevo y limpia la pantalla (no borra la base de datos).

**Columna derecha: panel lateral** (un tercio del ancho)
- Tres pestañas con los nombres de `panel.pestanas`: Citas, Tareas pendientes, Cotizaciones. Cada una muestra su contador (`panel.contadores`) y una lista de tarjetas compactas con los campos de `/api/panel`. Si la lista está vacía muestra `panel.vacio`.
- Solo lectura. Se actualiza al abrir la página y después de cada respuesta del asistente.
- Un cambio visible (por ejemplo, un resaltado breve) en la tarjeta nueva, para que se note en el video cuando aparece una cita o una tarea.

**Comportamiento**
- `hilo_id` se genera con `crypto.randomUUID()` y se guarda en `sessionStorage` (envuelto en try/catch; si falla, vive en una variable).
- Cada petición a `/api/chat` tiene un tiempo máximo de 180 segundos. Si falla la conexión o vence: mostrar como burbuja del asistente "No pude conectarme con el asistente. ¿Está encendido el modelo (qwen.sh)?" y volver a habilitar la caja de texto.
- Si el panel falla, mostrar el panel vacío sin romper el chat.
- Accesibilidad básica: etiquetas en la caja y botones, foco visible, contraste legible.

## Fuera de alcance

Login, adjuntos, respuesta palabra por palabra (streaming), versión móvil, edición de datos desde el panel, estadísticas.

## Criterios de aceptación

1. `uvicorn app.api.main:app --port 8000` arranca sin errores con el modelo apagado (muestra la advertencia) y con el modelo encendido.
2. `curl http://127.0.0.1:8000/api/salud` devuelve `{"api": true, "modelo": true}` con el modelo encendido.
3. `curl -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"mensaje":"Hola","hilo_id":"prueba"}'` devuelve el saludo.
4. `curl http://127.0.0.1:8000/api/panel` devuelve las tres listas y los tres contadores; tras reiniciar los datos muestra `CITA-0001` en `citas` y contadores `1, 0, 0`.
5. En el navegador se ve el chat con el saludo, los tres chips, el panel con las tres pestañas y sus contadores. Al enviar el mensaje del caso P1-01 aparece "Pensando...", luego la respuesta, y tras confirmar aparece `CITA-0002` en el panel y el contador sube a 2.
6. Una derivación (caso P1-04) aparece como tarjeta en "Tareas pendientes" y el contador sube.
7. Con el modelo apagado el chat muestra el mensaje de error amable, no se queda en "Pensando...".
8. El HTML no carga ningún recurso externo (revisar la pestaña de red del navegador).
