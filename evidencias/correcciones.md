# Correcciones de casos que fallaron

## P1-02 — La cita ya existe (idempotencia)

- Corridas fallidas conservadas: `evidencias/2026-10-16_2306_resultados_2.md` (0 de 1 casos pasan) y `evidencias/2026-10-16_2314_resultados.md` (0 de 1 casos pasan). En la primera el mensaje del cliente quedó registrado y la respuesta del asistente fue: "su solicitud ya existe con esos datos. La cita está programada para el 20 de octubre de 2026 a las 08:00 AM en la bahía B1 con el técnico Carlos Vega".
- Qué falló:
  1. La aserción "validar_solicitud devolvió estado ya_existe" no se podía comprobar: `app/agentes/trazas.py` no registraba el resultado de las herramientas porque dentro de un agente LangChain el callback recibe un `ToolMessage` y el código no desenvolvía su contenido. Las trazas solo guardaban el código "OK" y la aserción no encontraba el campo `estado`.
  2. La respuesta del asistente no incluía el código de la cita existente (`CITA-0001`), que el caso espera según `datos/pruebas/casos_chat.md` ("Responde que la cita ya existe: CITA-0001, 2026-10-20 08:00, bahia B1").
- Causa probable: (1) fallo de la infraestructura de pruebas (trazas incompletas); (2) el campo `que_hacer` del estado `ya_existe` no pedía mencionar el código de la cita, y el modelo de 4B no lo incluía por su cuenta.
- Qué se cambió:
  1. `app/agentes/trazas.py`: `_cuerpo` desenvuelve el `ToolMessage` y cada evento de herramienta guarda ahora el campo `resultado` (necesario para las aserciones de la especificación 05).
  2. `app/mcp_citas/logica.py`: el `que_hacer` del estado `ya_existe` (validador y confirmación) ahora pide informar "…y su codigo (id_cita)…".
- Repetición: `python scripts/correr_casos.py --caso P1-02` → PASA (`evidencias/2026-10-16_2314_resultados_2.md`); después se repitió la serie completa.

## P1-03 — Sin cupo: tres fechas alternativas

- Corrida fallida conservada: `evidencias/2026-10-16_2319_resultados.md` (9 de 14). La respuesta fue "Lo siento, Ana, no hay cupo para el 22 de octubre. ¿Te gustaría agendar para el 23, 26 o 27 de octubre a las 8:00?"; fallaron las tres aserciones de fechas (`2026-10-23`, `2026-10-26` y `2026-10-27`).
- Qué falló: el modelo parafraseaba las fechas alternativas ("23, 26 o 27 de octubre") en vez de copiarlas en formato AAAA-MM-DD.
- Causa probable: `consultar_disponibilidad` devolvía las alternativas como datos sueltos, sin un texto listo para copiar, y su `que_hacer` no pedía copiarlo tal cual.
- Qué se cambió: `app/mcp_citas/logica.py` → `consultar_disponibilidad` (estado `SIN_CUPO`) devuelve `alternativas_texto` con las tres fechas y horas, y su `que_hacer` pide al agente copiarlo tal cual, sin traducirlo ni reformatearlo.
- Repetición: PASA en todas las series posteriores (`0008`, `0013`, `0016`, `0019`, `0029`, `0039`, `0041`).

## P1-06 — Datos inválidos

- Corrida fallida conservada: `evidencias/2026-10-16_2319_resultados.md`. El cliente envió los datos con errores ("Placa ABC123, preventivo_15000, 2026-10-01, telefono 12345, me llamo Juan Perez") y el asistente respondió con un saludo, sin llamar ninguna herramienta; falló "validar_solicitud devolvió los 4 códigos en una sola respuesta".
- Causa probable: el orquestador no reconoció ese mensaje como solicitud de cita (no traía la palabra "cita" ni "preventivo" bien escrita) y lo trató como una conversación cualquiera.
- Qué se cambió: una línea del prompt del orquestador (`app/agentes/prompts.py`): si el mensaje trae datos de una cita o una cotización (nombre, placa, fecha, servicio, teléfono), aunque no lo pida con esas palabras, se llama al agente que corresponda.
- Repetición: PASA en todas las series posteriores.

## P1-08 — Fuera de alcance

- Corrida fallida conservada: `evidencias/2026-10-16_2319_resultados.md`. El asistente derivó a un asesor, pero (1) falló la aserción de la "única herramienta de citas llamada" y (2) la respuesta no contenía "no puedo".
- Causa probable: (1) la aserción contaba también el evento del orquestador (`orquestador: agente_citas`) como herramienta de citas; (2) el `que_hacer` de la derivación no pedía explicar que el chat no puede hacer esa gestión.
- Qué se cambió: (1) la aserción se ajustó (aprobado) para contar solo las herramientas del servidor MCP de citas (`trazas.HERRAMIENTAS_CITAS`); (2) `app/mcp_citas/logica.py` → `QUE_HACER_FUERA_DE_ALCANCE` pide "Explica al cliente que no puedes cancelar ni reprogramar citas desde este chat y que un asesor lo contactara…", y la línea correspondiente del prompt del agente de citas.
- Repetición: PASA en todas las series posteriores.

## P2-03 — Acepta la cotización (confirmación en dos pasos)

- Corridas fallidas conservadas:
  - `2026-10-16_2319_resultados.md`: "acepto la cotizacion" programó la orden en el mismo turno (OT-0001 en el turno 3); fallaron "Turno 3: no se llamó programar_servicio" y "Turno 3: la respuesta pide confirmación".
  - `2026-10-17_0008_resultados.md`: la guarda bloqueó la programación (`ESPERAR_CONFIRMACION`) pero el texto respondió "¿La acepta?" en vez de la pregunta de confirmación aprobada; en el turno 4 el bloqueo se repitió ("Sí, confirmo." no alcanzó) y fallaron "Turno 3: la respuesta pide confirmación" y "Turno 4: programar_servicio(OK)".
  - `2026-10-17_0013_resultados.md` y `2026-10-17_0016_resultados.md` (respuesta byte-idéntica): el orquestador enrutó "Esta bien, acepto la cotizacion de S/ 270." a `agente_citas`; el agente de citas respondió "como asistente de citas, no puedo procesar pagos ni aceptar cotizaciones…". Fallaron las aserciones del caso.
  - `2026-10-17_0029_resultados.md`: ya con la guarda del "flujo activo" aplicada, el orquestador volvió a enrutar ese mensaje a `agente_citas` (respuesta igual a `0013`/`0016`); falló "Turno 3: la respuesta pide confirmación".
- Causa probable: (1) faltaba la guarda de dos pasos y la pregunta exacta de confirmación; (2) el enrutado del 4B en los mensajes de seguimiento es intermitente: entre `0013`/`0016` (fallan, byte-idénticas) y `0019` (pasa) no se tocó código; `temperature=0` no reproduce la misma decisión de corrida a corrida.
- Qué se cambió:
  1. `app/agentes/guardas.py`: guarda de doble confirmación: `programar_servicio` con testigo responde `ESPERAR_CONFIRMACION` y no consume el testigo si la respuesta anterior no hace la pregunta de confirmación; `asegurar_pregunta` agrega "¿Confirmas que programe el servicio?" si el modelo no la hizo.
  2. `scripts/correr_casos.py`: aserciones del caso según la política de dos pasos (aprobado): turno 3 sin `programar_servicio` y con pregunta de confirmación; turno 4 con `programar_servicio(OK)`; además, foto del estado tras el turno 3 (`fotos[0]["ordenes2"] == []`).
  3. `app/agentes/guardas.py` y `app/agentes/orquestador.py`: guarda del "flujo activo" (spec 03): memoria del último agente por hilo y línea "Flujo activo: citas" / "Flujo activo: cotizacion" al inicio del mensaje del sistema del orquestador (prompt dinámico). Verificado por HTTP que la línea se entrega en los turnos de seguimiento.
- Repetición: PASA en `0019` (14/14, sin cambios de código respecto de `0013`/`0016`), `0039` (14/14) y `0041` (14/14); en `0029` (primera corrida con la guarda) falló una vez por enrutado. Con el enrutamiento de seguimiento determinista (sección siguiente) pasa en `0057`, `0059` y `0101`.

## P2-04 — Monto alto

- Corridas fallidas conservadas: `2026-10-16_2319_resultados.md` y `2026-10-16_2330_resultados.md` (0 de 1). El agente llamó `derivar_a_humano` tres veces y la respuesta fue "No pude completar tu solicitud. Un asesor la revisará."; falló "La respuesta contiene 2500".
- Causa probable: derivar volvía a encolar la excepción en cada llamada (bucle del 4B), y ni el `que_hacer` de `MONTO_REQUIERE_APROBACION` ni el de la derivación pedían informar el monto al cliente.
- Qué se cambió: `app/mcp_cotizaciones/logica.py` → `derivar_a_humano` idempotente (`_excepcion_de` reutiliza la excepción pendiente del mismo motivo), `QUE_HACER_DERIVACION` pide explicar el motivo y el total (`total_texto`), y el `que_hacer` de `MONTO_REQUIERE_APROBACION` incluye el monto y que lo aprueba el jefe de taller.
- Repetición: PASA en todas las series posteriores.

## Enrutamiento de seguimiento determinista (flujos de citas y cotización)

- Por qué: en los mensajes de seguimiento (por ejemplo, el turno 3 de P2-03: "Esta bien, acepto la cotizacion de S/ 270.") el orquestador (modelo de 4B) enrutaba de forma intermitente al agente equivocado: falló en `0013`, `0016` y `0029` (con `temperature=0`). La línea "Flujo activo" de la spec 03 se entregaba (verificado por HTTP), pero no era garantía: entre `0013`/`0016` y `0019` no se tocó código y el resultado cambió.
- Qué se cambió (solo código, sin tocar prompts, sin dependencias nuevas):
  1. `app/agentes/guardas.py`: estado por hilo `FLUJO_ABIERTO`; `fijar_agente` abre el flujo; `flujo_abierto(hilo)` lo consulta; `_cerrar_si_ok` marca el cierre cuando `confirmar_cita`, `programar_servicio` o `derivar_a_humano` responden OK (incluida la derivación interna por límite de iteraciones).
  2. `app/agentes/orquestador.py`: `_seguimiento(mensaje, hilo_id)` decide el camino; `responder` llama directo al agente del flujo abierto (mismo hilo `{hilo}:citas` o `{hilo}:cotizacion`, `recursion_limit` 12, mismas guardas y trazas). Reglas: si el mensaje trae "cotiz" con flujo de citas, o "cita" con flujo de cotización, decide el orquestador; los hilos sin flujo abierto van al orquestador como antes.
  3. `tests/test_guardas.py`: 4 pruebas sin modelo (flujo abierto llama directo, flujo cerrado vuelve al orquestador, `derivar_a_humano(OK)` también cierra, cambio de tema decide el orquestador). `pytest`: 33 pasan.
- Efecto: los turnos de seguimiento ya no dependen del enrutado del modelo: P1-01 turno 2 va directo al agente de citas; P2-02 y P2-03 (turnos 3 y 4) van directo al de cotización (visible en la evidencia: esos turnos no tienen evento `orquestador: agente_*`).
- Repetición: `0057`, `0059` y `0101` → 14 de 14 cada una, con la API del puerto 8000 reiniciada antes de la serie.

## Corridas conservadas

Ninguna corrida se borró ni editó. Archivos en `evidencias/`:

- `2026-10-16_2306_resultados.md` y `2026-10-16_2306_resultados_2.md` (P1-02 y P1-03 fallan).
- `2026-10-16_2314_resultados.md` (P1-02 falla) y `2026-10-16_2314_resultados_2.md` (P1-02 pasa).
- `2026-10-16_2319_resultados.md` (9 de 14: fallan P1-03, P1-06, P1-08, P2-03, P2-04).
- `2026-10-16_2330_resultados.md` (P2-04 falla).
- `2026-10-17_0008_resultados.md` (13 de 14: P2-03 falla con la frase "¿La acepta?" y el turno 4 sin programar).
- `2026-10-17_0013_resultados.md` (13 de 14: P2-03 falla por enrutado).
- `2026-10-17_0016_resultados.md` (13 de 14: P2-03 falla por enrutado).
- `2026-10-17_0019_resultados.md` (14 de 14).
- `2026-10-17_0029_resultados.md` (13 de 14: P2-03 falla por enrutado, con la guarda del flujo activo).
- `2026-10-17_0039_resultados.md` (14 de 14).
- `2026-10-17_0041_resultados.md` (14 de 14).
- `2026-10-17_0057_resultados.md` (14 de 14, con enrutamiento de seguimiento determinista).
- `2026-10-17_0059_resultados.md` (14 de 14).
- `2026-10-17_0101_resultados.md` (14 de 14).
