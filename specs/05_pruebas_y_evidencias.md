# Especificación 05 — Pruebas del chat, evidencias y trazabilidad

Requisito: las especificaciones 01 a 04 están terminadas. Los casos y sus mensajes salen de `datos/pruebas/casos_chat.md`; si algo de aquí lo contradice, gana ese archivo y avísame.

## `scripts/correr_casos.py`

Opciones: `--reiniciar` (por defecto activado: ejecuta `scripts/reiniciar_datos.py` antes de empezar), `--caso P1-03` (corre uno solo, sin reiniciar), `--url` (por defecto `http://127.0.0.1:8000`).

Cada caso usa un `hilo_id` propio, excepto P2-01, P2-02 y P2-03, que comparten uno. Se ejecutan en el orden de la tabla (P1-01 deja creada la `CITA-0002`). Para cada caso el script:
1. Envía los mensajes por `POST /api/chat`, uno por turno, y guarda cada respuesta.
2. Lee las herramientas llamadas en ese turno desde `var/trazas.jsonl` (nombre y código de resultado).
3. Comprueba las aserciones de la tabla de abajo, que se basan en las herramientas llamadas, el estado de las bases SQLite y algunas palabras clave de la respuesta (nunca en el texto exacto).
4. Escribe `evidencias/AAAA-MM-DD_HHMM_resultados.md`: una tabla con caso, escenario, mensajes, respuesta del asistente, herramientas llamadas, aserciones (cada una con PASA o FALLA) y un resultado global por caso. **Nunca sobrescribe** un archivo anterior: el nombre lleva fecha y hora, porque las pruebas que fallan y se corrigen deben conservar ambas corridas.
5. Termina con un resumen en consola (`12 de 14 casos pasan`) y código de salida distinto de cero si alguno falla.

## Aserciones por caso

Notación: "herramienta(CÓDIGO)" significa que esa herramienta fue llamada y devolvió ese código (`OK` si no hubo error). Un caso falla si cualquier aserción falla.

| Caso | Turnos | Aserciones |
| --- | --- | --- |
| P1-01 | 1. Mensaje del caso. 2. "Sí, confirmo." | Turno 1: `validar_solicitud(OK)` y `preparar_cita(OK)`; **no** se llamó `confirmar_cita`; la respuesta contiene "08:00". Turno 2: `confirmar_cita(OK)`; la tabla `citas` tiene `CITA-0002` con placa `A1B-234`, fecha `2026-10-21`, hora `08:00`, y la hora quedó `ocupado`. |
| P1-02 | 1 | `validar_solicitud` devolvió estado `ya_existe`; no hubo `preparar_cita` ni `confirmar_cita`; la tabla `citas` no cambió de tamaño; la respuesta contiene "CITA-0001". |
| P1-03 | 1 | Algún `consultar_disponibilidad` o `preparar_cita` devolvió `SIN_CUPO`; la respuesta contiene `2026-10-23`, `2026-10-26` y `2026-10-27`; no se creó cita. |
| P1-04 | 1 | `SIN_KIT` devuelto; `derivar_a_humano` llamado con motivo `SIN_KIT`; `cola_excepciones` del proceso 1 creció en 1; no se creó cita. |
| P1-05 | 1 | `REQUIERE_APROBACION` devuelto; `derivar_a_humano` llamado con motivo `REQUIERE_APROBACION`; la cola creció en 1; no se creó cita. |
| P1-06 | 1 | `validar_solicitud` devolvió los códigos `PLACA_INVALIDA`, `TIPO_INVALIDO`, `FECHA_INVALIDA` y `TELEFONO_INVALIDO` en una sola respuesta; **no** se llamó `consultar_disponibilidad`. |
| P1-07 | 1 | `validar_solicitud` devolvió estado `posible_falla`; `derivar_a_humano` llamado con motivo `POSIBLE_CORRECTIVO`; no se creó cita. |
| P1-08 | 1 | La única herramienta de citas llamada es `derivar_a_humano` (motivo `FUERA_DE_ALCANCE`); la respuesta contiene "no puedo" (sin importar mayúsculas); no se creó ni cambió ninguna cita. |
| P2-01 | 1 | `consultar_tarifario(OK)` con `FRE-01`; `armar_cotizacion(OK)`; `validar_politica_comercial(OK)`; la respuesta contiene "270"; `cotizaciones` tiene `COT-0001` en estado `validada`. |
| P2-02 | 2. "Dame 10% de descuento en esa cotización." (mismo hilo que P2-01) | `validar_politica_comercial` llamada con descuento mayor a 0 y con `aviso` `DESCUENTO_NO_PERMITIDO`; la respuesta contiene "270"; no hay cotización nueva. |
| P2-03 | 3. "Esta bien, acepto la cotización de S/ 270." 4. "Sí, confirmo." | Turno 3: **no** se llamó `programar_servicio`; la respuesta pide confirmación. Turno 4: `programar_servicio(OK)`; existe `OT-0001` ligada a `COT-0001`; `COT-0001` quedó `aceptada`. |
| P2-04 | 1 | `consultar_tarifario` devolvió `EMB-01` y `DIS-01`; `validar_politica_comercial(MONTO_REQUIERE_APROBACION)`; `derivar_a_humano` llamado con ese motivo; la respuesta contiene "2500"; no se creó orden. |
| P2-05 | 1 | `consultar_tarifario(SERVICIO_NO_ENCONTRADO)`; **no** se llamó `armar_cotizacion`; la respuesta no contiene ningún monto del tipo `S/ <número>`. |
| P2-06 | 1 | No se llamó ninguna herramienta de los servidores MCP; la respuesta menciona "cita" y "cotiz". |

Pruebas sin modelo que `correr_casos.py` también ejecuta al inicio y registra en el mismo archivo: la clave de `T4M891|2026-09-22|preventivo_10000` es `1b114e68d6a3241784560e39cf0868d9`; confirmar con un testigo ya usado devuelve `TESTIGO_INVALIDO` con `que_hacer`; enviar dos veces la misma solicitud deja un solo registro.

## Evidencia de un caso fallido que se corrige

El Lab 02 pide evidencia de un caso exitoso y uno fallido. Con un modelo de 4B es probable que alguna corrida falle. Cuando falle un caso:
1. Conserva el archivo de esa corrida (no lo borres ni lo edites).
2. Anota en `evidencias/correcciones.md`: caso, qué falló, causa probable y qué se cambió. Los cambios permitidos son el docstring de una herramienta, el campo `que_hacer` de un error o una línea del prompt; no cambies las reglas de negocio ni los datos.
3. Vuelve a correr solo ese caso (`--caso`) y luego la serie completa.
Si todos pasan a la primera, provoca un caso fallido a propósito (por ejemplo, quitando temporalmente el "cuándo NO usar" del docstring de `confirmar_cita`), guarda esa corrida, restaura el docstring y vuelve a correr.

## `docs/trazabilidad.md`

Una tabla con las columnas: elemento del BPMN, herramienta o agente, archivo y función, caso de prueba que lo ejercita. Usa la tabla de trazabilidad del proceso 1 que está en `AGENTS.md` (con su nombre y su id del BPMN) y agrégale el archivo, la función y el caso (por ejemplo, `S1v` → `validar_solicitud` → `app/mcp_citas/logica.py` → P1-06). Para el proceso 2, deja las filas con las herramientas y los casos, y la columna del elemento del BPMN con el texto "completar con el TO-BE de cotización". Incluye también filas para el orquestador, los dos agentes y las guardas (guarda de turno, límite de iteraciones, salida inválida, modelo apagado) con el patrón de la S05 que implementan.

## Comprobaciones finales

1. `pytest` (todas las pruebas de 01, 02 y la guarda de turno de 03) pasa completo.
2. `python scripts/correr_casos.py` termina con los 14 casos en PASA y deja un archivo en `evidencias/`.
3. Existe al menos un archivo de evidencia con un caso fallido y la entrada correspondiente en `evidencias/correcciones.md`.
4. `docs/trazabilidad.md` no tiene filas vacías, salvo la columna del BPMN del proceso 2.
5. `grep -rn "api_key\|sk-" app/ scripts/` no muestra ninguna clave real (solo la clave falsa de `llm.py`).
6. `datos/` no cambió.
7. El `.env` está en `.gitignore`, igual que `var/` y `.venv/`.
