# Inventario de agentes

Generado por `scripts/inventario_agentes.py` leyendo `app/agentes/` y los servidores MCP.

## Aclaracion de arquitectura

- El **orquestador es un agente supervisor** creado con `create_agent` de LangChain 1.x. Solo tiene dos herramientas (`agente_citas` y `agente_cotizacion`) con `return_direct=True`.
- El **agente de citas** y el **agente de cotizacion** son **subagentes** creados tambien con `create_agent`; cada uno recibe solo las 5 herramientas de su servidor MCP.
- **NO se usa el paquete `deepagents`**. La verificacion con `importlib.util.find_spec("deepagents")` devuelve: no instalado (None).
- La memoria es un `InMemorySaver` compartido por hilo; cada subagente usa `{hilo_id}:citas` o `{hilo_id}:cotizacion`.

## Resumen

| Agente | Rol | Modelo | Herramientas | recursion_limit | Checkpointer | return_direct |
| --- | --- | --- | --- | --- | --- | --- |
| Orquestador (supervisor) | Eres el asistente de Autonorte Servicios Automotrices. Atiendes por chat en español, con un tono amable y breve. | `qwen` local | 2 (`agente_citas`, `agente_cotizacion`) | 8 cuando decide el orquestador; 12 cuando atiende directo un flujo abierto | InMemorySaver | Si, en sus 2 herramientas |
| Agente de citas (subagente) | Eres el agente de citas de Autonorte. Agendas citas de mantenimiento preventivo usando solo tus herramientas. Hablas en español, breve y amable. | `qwen` local | 5 MCP de citas | 12 | InMemorySaver | No |
| Agente de cotizacion (subagente) | Eres el agente de cotizaciones de Autonorte. Cotizas reparaciones correctivas usando solo tus herramientas. Hablas en español, breve y amable. | `qwen` local | 5 MCP de cotizaciones | 12 | InMemorySaver | No |

## Orquestador (supervisor)

**Rol:** Eres el asistente de Autonorte Servicios Automotrices. Atiendes por chat en español, con un tono amable y breve.

**Modelo:** ChatOpenAI local de `get_llm()`: `MODEL_BACKEND=llamacpp`, `MODEL_NAME=qwen`, `base_url=http://localhost:8080/v1`, `temperature=0`.

**Herramientas:**

| Herramienta | Primera linea del docstring / descripcion | Archivo y linea |
| --- | --- | --- |
| `agente_citas` | Agenda una cita de mantenimiento preventivo. Úsala para agendar, cambiar o cancelar citas. NO la uses para cotizar reparaciones. | `app/agentes/orquestador.py:27` |
| `agente_cotizacion` | Cotiza una reparación correctiva del vehículo. Úsala para precios o fallas. NO la uses para agendar citas de mantenimiento preventivo. | `app/agentes/orquestador.py:37` |

**Prohibiciones del prompt:**

- No inventes precios, fechas, horas, ids ni datos del cliente.
- No respondas sobre otros temas (política, consejos mecánicos, otras empresas). Di que solo ayudas con citas y cotizaciones.
- No llames a un agente si el cliente no pidió una cita ni una cotización.
- No cambies el mensaje del cliente al pasarlo al agente.

**recursion_limit:** 8 cuando decide el orquestador; 12 cuando atiende directo un flujo abierto

**Checkpointer:** InMemorySaver compartido en `app/agentes/__init__.py` (`MEMORIA`); el estado vive en memoria del proceso. Hilo: `hilo_id` (o `{hilo_id}:{agente}` cuando atiende un flujo abierto).

**return_direct:** Si: `agente_citas` y `agente_cotizacion` tienen `return_direct=True`.

## Agente de citas (subagente)

**Rol:** Eres el agente de citas de Autonorte. Agendas citas de mantenimiento preventivo usando solo tus herramientas. Hablas en español, breve y amable.

**Modelo:** ChatOpenAI local de `get_llm()`: `MODEL_BACKEND=llamacpp`, `MODEL_NAME=qwen`, `base_url=http://localhost:8080/v1`, `temperature=0`.

**Herramientas:**

| Herramienta | Primera linea del docstring / descripcion | Archivo y linea |
| --- | --- | --- |
| `validar_solicitud` | Valida los 5 datos del cliente y guarda la solicitud con su clave. | `app/mcp_citas/server.py:28` |
| `consultar_disponibilidad` | Consulta fecha de agenda, kit, cupo y duracion para una clave validada. | `app/mcp_citas/server.py:45` |
| `preparar_cita` | Verifica otra vez todo y emite el testigo de un solo uso para confirmar. | `app/mcp_citas/server.py:53` |
| `confirmar_cita` | Registra la cita consumiendo el testigo que emitio preparar_cita. | `app/mcp_citas/server.py:61` |
| `derivar_a_humano` | Encola el caso para que un asesor lo revise. | `app/mcp_citas/server.py:69` |

**Prohibiciones del prompt:**

- No inventes ni calcules horas, fechas, bahías, técnicos ni ids de cita: usa solo lo que devuelven las herramientas.
- Escribe las fechas tal como te las dan las herramientas, en formato AAAA-MM-DD; no las conviertas a texto.
- No llames confirmar_cita en el mismo mensaje en que mostraste el resumen.
- Antes de confirmar_cita, no digas que la cita está reservada ni confirmada: di que la propones.
- No cancelas ni reprogramas citas: explica al cliente que no puedes cancelar y llama derivar_a_humano con motivo FUERA_DE_ALCANCE.
- No des consejos mecánicos ni hables de precios de reparación.
- Si una herramienta devuelve un error, explícalo con tus palabras y sigue su "que_hacer"; no insistas con los mismos datos.

**recursion_limit:** 12

**Checkpointer:** InMemorySaver compartido en `app/agentes/__init__.py` (`MEMORIA`); el estado vive en memoria del proceso. Hilo: `{hilo_id}:citas`.

**return_direct:** No: las herramientas MCP no declaran `return_direct`.

## Agente de cotizacion (subagente)

**Rol:** Eres el agente de cotizaciones de Autonorte. Cotizas reparaciones correctivas usando solo tus herramientas. Hablas en español, breve y amable.

**Modelo:** ChatOpenAI local de `get_llm()`: `MODEL_BACKEND=llamacpp`, `MODEL_NAME=qwen`, `base_url=http://localhost:8080/v1`, `temperature=0`.

**Herramientas:**

| Herramienta | Primera linea del docstring / descripcion | Archivo y linea |
| --- | --- | --- |
| `consultar_tarifario` | Busca en el tarifario por palabras clave de la falla o del servicio. | `app/mcp_cotizaciones/server.py:28` |
| `armar_cotizacion` | Arma la cotizacion con los precios del tarifario y calcula el total. | `app/mcp_cotizaciones/server.py:36` |
| `validar_politica_comercial` | Valida el monto y el descuento contra la politica comercial y emite el testigo. | `app/mcp_cotizaciones/server.py:44` |
| `programar_servicio` | Consume el testigo y crea la orden de trabajo solo si el cliente confirma. | `app/mcp_cotizaciones/server.py:52` |
| `derivar_a_humano` | Encola el caso para un asesor con la cotizacion y los pasos previos. | `app/mcp_cotizaciones/server.py:60` |

**Prohibiciones del prompt:**

- No inventes ni calcules precios, totales, ids ni códigos de servicio: usa solo lo que devuelven las herramientas.
- Escribe siempre los montos en soles con el formato S/, nunca con $.
- No ofrezcas descuentos ni los prometas: la tarifa es fija.
- No llames programar_servicio cuando el cliente acepta la cotización: primero pídele que confirme y espera su siguiente mensaje.
- No agendes citas de mantenimiento preventivo: dile al cliente que para eso hay otra opción en este chat.
- Si no encuentras el servicio, no adivines un precio: pide otra descripción o llama derivar_a_humano.

**recursion_limit:** 12

**Checkpointer:** InMemorySaver compartido en `app/agentes/__init__.py` (`MEMORIA`); el estado vive en memoria del proceso. Hilo: `{hilo_id}:cotizacion`.

**return_direct:** No: las herramientas MCP no declaran `return_direct`.
