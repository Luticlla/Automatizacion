# Especificación 03 — Modelo, agentes y orquestador

Requisito: las especificaciones 01 y 02 están terminadas y sus pruebas pasan.
Verifica con la versión instalada (`pip show langchain langgraph langchain-openai langchain-mcp-adapters mcp`) las firmas de `create_agent` (langchain 1.x) o `create_react_agent` (`langgraph.prebuilt`), de `MultiServerMCPClient` y de `InMemorySaver`. Usa la que exista; no asumas la API de memoria.

## `app/llm.py`

`get_llm()` devuelve un `ChatOpenAI` de `langchain-openai` con `base_url=MODEL_BASE_URL`, `api_key="sin-clave"`, `model=MODEL_NAME`, `temperature=0`, `timeout=120`, `max_retries=1`. Si `MODEL_BACKEND` no es `llamacpp`, lanza un error claro: la nube solo se activa con aprobación expresa del equipo. `comprobar_modelo()` hace `GET {MODEL_BASE_URL}/models` y devuelve verdadero o falso. El servidor `qwen.sh` ya desactiva el razonamiento (`--reasoning off`); no se hace nada más al respecto.

## Cliente MCP

`app/agentes/mcp_clientes.py` define dos servidores stdio con `sys.executable -m app.mcp_citas.server` y `-m app.mcp_cotizaciones.server`, ejecutados desde la raíz del proyecto y con el entorno del proceso actual. Se cargan las herramientas de cada servidor **por separado**: el agente de citas solo recibe las de citas, y el de cotización solo las de cotización.
Si cada llamada a una herramienta lanza un subproceso nuevo y tarda más de 1 segundo, usar sesiones persistentes abiertas al arrancar la API (lifespan de FastAPI). Esto es seguro porque todo el estado vive en SQLite.

## Prompts (`app/agentes/prompts.py`)

Usa estos textos tal cual. Son cortos a propósito; no los alargues.

### Orquestador
```
Eres el asistente de Autonorte Servicios Automotrices. Atiendes por chat en español, con un tono amable y breve.
Solo puedes ayudar con dos cosas: agendar una cita de mantenimiento preventivo y cotizar una reparación.

Cómo trabajas:
- Si el cliente quiere agendar, cambiar o cancelar una cita de mantenimiento, llama a agente_citas.
- Si el cliente quiere el precio de una reparación o describe una falla del vehículo, llama a agente_cotizacion.
- Cuando llames a un agente, pasa en "consulta" el mensaje del cliente copiado tal cual, sin resumirlo ni corregirlo.
- Si ya estás en medio de una cita o una cotización y el cliente responde algo corto (sí, no, una fecha, un dato), llama al mismo agente de antes con ese mensaje.
- Si el cliente solo saluda o pregunta qué puedes hacer, responde tú: saluda y explica en una frase las dos cosas que haces.

Prohibido:
- No inventes precios, fechas, horas, ids ni datos del cliente.
- No respondas sobre otros temas (política, consejos mecánicos, otras empresas). Di que solo ayudas con citas y cotizaciones.
- No llames a un agente si el cliente no pidió una cita ni una cotización.
- No cambies el mensaje del cliente al pasarlo al agente.
```

### Agente de citas
```
Eres el agente de citas de Autonorte. Agendas citas de mantenimiento preventivo usando solo tus herramientas. Hablas en español, breve y amable.

Datos que debes pedir al cliente (uno o varios a la vez, sin repetir lo que ya te dio):
nombre completo, teléfono, placa, tipo de servicio (preventivo_5000, preventivo_10000 o preventivo_20000) y fecha deseada en formato AAAA-MM-DD.
Si el cliente cuenta un problema del vehículo, pásalo en "descripcion". No preguntes por el canal ni por el correo.

Pasos:
1. Cuando tengas los cinco datos, llama validar_solicitud.
2. Sigue siempre el campo "que_hacer" de cada respuesta de herramienta.
3. Cuando preparar_cita te dé el resumen, muéstralo y pregunta si confirma. Espera su respuesta.
4. Solo si el cliente responde que sí en un mensaje nuevo, llama confirmar_cita con el testigo.

Prohibido:
- No inventes ni calcules horas, fechas, bahías, técnicos ni ids de cita: usa solo lo que devuelven las herramientas.
- No llames confirmar_cita en el mismo mensaje en que mostraste el resumen.
- No cancelas ni reprogramas citas: llama derivar_a_humano con motivo FUERA_DE_ALCANCE.
- No des consejos mecánicos ni hables de precios de reparación.
- Si una herramienta devuelve un error, explícalo con tus palabras y sigue su "que_hacer"; no insistas con los mismos datos.
```

### Agente de cotización
```
Eres el agente de cotizaciones de Autonorte. Cotizas reparaciones correctivas usando solo tus herramientas. Hablas en español, breve y amable.

Datos que necesitas: marca y modelo del vehículo, y la falla o el servicio que necesita. La placa es opcional.

Pasos:
1. Con la descripción de la falla, llama consultar_tarifario.
2. Con el código elegido, llama armar_cotizacion.
3. Llama validar_politica_comercial con el id de la cotización. Si el cliente pidió descuento, envía el porcentaje en descuento_solicitado_pct.
4. Informa la cotización (servicios, precio de cada uno y total) y pregunta si la acepta. Espera su respuesta.
5. Solo si el cliente responde en un mensaje nuevo: si acepta, confirma una vez más ("¿Confirmas que programe el servicio?"); con su sí, llama programar_servicio con decision aceptar. Si rechaza, llama programar_servicio con decision rechazar.
Sigue siempre el campo "que_hacer" de cada respuesta de herramienta.

Prohibido:
- No inventes ni calcules precios, totales, ids ni códigos de servicio: usa solo lo que devuelven las herramientas.
- No ofrezcas descuentos ni los prometas: la tarifa es fija.
- No llames programar_servicio en el mismo mensaje en que informaste la cotización.
- No agendes citas de mantenimiento preventivo: dile al cliente que para eso hay otra opción en este chat.
- Si no encuentras el servicio, no adivines un precio: pide otra descripción o llama derivar_a_humano.
```

## Agentes como herramientas

`app/agentes/citas.py` y `app/agentes/cotizacion.py`: cada uno construye un agente con herramientas (LLM de `get_llm()`, sus 5 herramientas MCP, su prompt, el `InMemorySaver` compartido) y expone una función asíncrona `consultar(consulta, hilo_id)` que lo invoca con:
- `{"messages": [("user", consulta)]}`,
- `config = {"configurable": {"thread_id": f"{hilo_id}:citas"}, "recursion_limit": 12}` (o `:cotizacion`),
- y devuelve el texto de la última respuesta del modelo.

`app/agentes/orquestador.py` define dos herramientas con `StructuredTool`:
- `agente_citas(consulta: str)` y `agente_cotizacion(consulta: str)`, ambas con `return_direct=True` y descripciones del tipo: "Agenda una cita de mantenimiento preventivo. Úsala para agendar, cambiar o cancelar citas. NO la uses para cotizar reparaciones."
- El `hilo_id` actual llega por una variable de contexto (`contextvars`) que fija la API antes de invocar.
El orquestador es un agente con esas dos herramientas, el prompt del orquestador, `recursion_limit=8` y el mismo `InMemorySaver` con `thread_id = hilo_id`.

Función pública: `async def responder(mensaje: str, hilo_id: str) -> str`.

## Guardas (`app/agentes/guardas.py`)

1. **Guarda de turno.** Estado por solicitud en una variable de contexto: el conjunto de testigos emitidos en el turno actual. Se vacía al inicio de cada `responder`. Se envuelven las herramientas:
   - `preparar_cita` y `validar_politica_comercial`: si la respuesta trae `testigo`, se agrega al conjunto.
   - `confirmar_cita` y `programar_servicio`: si el testigo recibido está en el conjunto, **no se llama al servidor** y se devuelve `{"ok": false, "codigo": "ESPERAR_CONFIRMACION", "mensaje": "El cliente todavía no confirmó.", "que_hacer": "Muestra el resumen al cliente, pide que confirme y termina tu respuesta. No llames más herramientas.", "clase": "datos"}`.
2. **Límite de iteraciones.** Si el agente lanza `GraphRecursionError`: se llama a `derivar_a_humano` del servidor correspondiente con `motivo="LIMITE_DE_ITERACIONES"` y la consulta original, y se responde: "No pude completar tu solicitud. Un asesor la revisará."
3. **Salida inválida.** Si el texto final está vacío, o contiene restos como `<tool_call>` o `<think>`, se reintenta una vez la misma invocación. Si persiste, se deriva igual que en el punto 2 con `motivo="ERROR_DE_SISTEMA"`.
4. **Modelo apagado.** Si no hay conexión con el modelo, `responder` devuelve: "No puedo responder ahora porque el modelo no está encendido." sin lanzar excepción.
5. **Errores inesperados**: capturar, registrar con el traceback en `var/trazas.jsonl` y responder con un mensaje genérico amable.

## Trazas (`app/agentes/trazas.py`)

Un callback de LangChain que escribe una línea JSON por evento en `var/trazas.jsonl` (y un resumen corto en consola del proceso de la API): hora, `hilo_id`, agente, nombre de la herramienta, argumentos, código de resultado (`ok` o `codigo`) y el texto de la respuesta final. Es la evidencia de las pruebas y lo que se muestra en el video. No registrar el texto completo de los prompts.

## Criterios de aceptación

Escribe `scripts/probar_agentes.py` que, con el modelo encendido, ejecute estas conversaciones en consola mostrando cada mensaje, la respuesta y las herramientas llamadas:

1. "Hola, buenas tardes" → saluda y explica las dos opciones; sin herramientas.
2. "Quiero cita de preventivo 10000 para mi placa A1B-234 el 2026-10-21. Soy Marco Ruiz Delgado, telefono 987654321." → muestra el resumen con 08:00; **no** llama `confirmar_cita`. Luego "Sí, confirmo." → llama `confirmar_cita` y responde con `CITA-0002`.
3. "Mi Toyota Hilux frena mal y hace ruido al frenar." → cotiza S/ 270.
4. Un mensaje fuera de tema ("¿Quién ganó el partido de ayer?") → responde que solo ayuda con citas y cotizaciones; sin herramientas.

Además:
- La guarda de turno se prueba con una prueba unitaria sin modelo (testigo emitido y confirmado en el mismo turno → `ESPERAR_CONFIRMACION`).
- Con `qwen.sh` apagado, `responder` devuelve el mensaje del punto 4 de las guardas, sin traceback.
- Antes de ejecutar `probar_agentes.py`, corre `python scripts/reiniciar_datos.py`.
- Si el orquestador no mantiene el agente correcto en los mensajes de seguimiento ("sí", una fecha), no alargues su prompt: guarda en memoria del proceso el último agente usado por hilo y agrégalo como una línea al inicio del mensaje del sistema ("Flujo activo: citas"). Avísame antes de hacer este cambio.
