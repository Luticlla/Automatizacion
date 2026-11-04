# Especificación 02 — Servidor MCP de cotizaciones

Requisito: la especificación 01 está terminada (`config.py`, `db.py`, `comun.py` existen).
Lee antes: `datos/proceso2_cotizacion_correctiva/reglas_negocio.md`, `tarifario.csv` y `politicas_comerciales.csv`. Esas reglas son la fuente.

## Base de datos del proceso 2

Agrega a `app/db.py` la función `reiniciar_proceso2()` (y que `iniciar_si_no_existen()` y `scripts/reiniciar_datos.py` la llamen). Crea `var/proceso2.db` cargando los dos CSV. Tablas:

- `tarifario(codigo PK, servicio, mano_obra_soles, repuestos_soles, precio_total_soles, duracion_horas, palabras_clave)`.
- `politicas(regla PK, valor, fuente)`.
- `cotizaciones(id_cotizacion PK, vehiculo, placa, lineas_json, total, estado, creada_en)`. Estados: `validada`, `pendiente_aprobacion`, `aceptada`, `rechazada`.
- `ordenes_trabajo(id_ot PK, id_cotizacion, estado, creada_en)`.
- `testigos`, `cola_excepciones`, `bitacora`: mismas columnas que en el proceso 1 (reutiliza las funciones de `comun.py` pasándoles la conexión de esta base).
- Ids: `COT-0001`, `OT-0001`, `EXC-0001`, secuenciales con 4 dígitos.

## Servidor MCP

Archivos: `app/mcp_cotizaciones/logica.py` y `app/mcp_cotizaciones/server.py` (FastMCP, stdio). Se arranca con `python -m app.mcp_cotizaciones.server`. Mismas reglas de oro que en la especificación 01: sin excepciones, sin `print` a stdout, errores con `ok`, `codigo`, `mensaje`, `que_hacer`, `clase`.

### Las 5 herramientas

**1. `consultar_tarifario(descripcion)`**
Normaliza la descripción (minúsculas, sin tildes) y busca servicios cuyas `palabras_clave` (separadas por `;`, también normalizadas) aparezcan como subcadena. Devuelve las coincidencias ordenadas por número de palabras clave encontradas: `{"ok": true, "coincidencias": [{"codigo", "servicio", "precio_total_soles"}], "que_hacer": "..."}`.
- Una coincidencia: `que_hacer` = "Llama armar_cotizacion con ese código."
- Varias: `que_hacer` = "Si el cliente pidió varios servicios, usa todos los códigos. Si describió una sola falla, muestra las opciones y pregunta cuál."
- Ninguna: `SERVICIO_NO_ENCONTRADO` con `que_hacer` de `reglas_negocio.md`.
Docstring: NO se usa para dar precios inventados ni para citas de mantenimiento preventivo.

**2. `armar_cotizacion(codigos, vehiculo, placa="")`**
`codigos` es una lista de códigos del tarifario. Valida que existan todos (si no: `SERVICIO_NO_ENCONTRADO`). Calcula las líneas y el total **en código** con el precio del tarifario y crea la cotización con el siguiente `COT-XXXX`, estado `validada`. Devuelve `{"ok": true, "id_cotizacion", "vehiculo", "lineas": [{codigo, servicio, precio}], "total", "que_hacer": "Llama validar_politica_comercial con el id_cotizacion."}`. El modelo no envía precios ni totales.

**3. `validar_politica_comercial(id_cotizacion, descuento_solicitado_pct=0)`**
Lee la política de la tabla `politicas` (`descuento_maximo_pct` = 0, `monto_maximo_sin_aprobacion_soles` = 2000). Es determinista: no usa modelo.
- Total mayor que el monto máximo: estado `pendiente_aprobacion`, devuelve `MONTO_REQUIERE_APROBACION` con `que_hacer`: "Llama derivar_a_humano con motivo='MONTO_REQUIERE_APROBACION' y el id_cotizacion; explica que lo aprueba el jefe de taller." No emite testigo.
- Si pasa: invalida los testigos anteriores de esa cotización, emite uno nuevo con acción `cotizacion` y devuelve `{"ok": true, "id_cotizacion", "total", "vigencia_dias": 7, "testigo": "T-XXXXXXXX", "que_hacer": "Informa la cotización al cliente y pregunta si la acepta. NO llames programar_servicio hasta que el cliente responda en un mensaje nuevo."}`.
- Si además `descuento_solicitado_pct` es mayor que el máximo permitido, agrega `"aviso": {"codigo": "DESCUENTO_NO_PERMITIDO", "mensaje": "La política no permite descuentos.", "que_hacer": "Informa la tarifa fija sin descuento."}`. El total no cambia nunca.

**4. `programar_servicio(testigo, decision="aceptar")`**
`decision` es `aceptar` o `rechazar`; cualquier otro valor devuelve un error de datos con `que_hacer` que lista los dos valores. En una transacción consume el testigo (si falla: `TESTIGO_INVALIDO`, "Vuelve a llamar validar_politica_comercial").
- `aceptar`: cotización a `aceptada`, crea la orden `OT-XXXX` en estado `programada` y devuelve `{"ok": true, "id_cotizacion", "id_ot", "total", "que_hacer": "Confirma al cliente la orden de trabajo y avisa que el taller lo llamará para coordinar la fecha."}`.
- `rechazar`: cotización a `rechazada`, sin orden, `que_hacer`: "Despídete del cliente y ofrécele otra ayuda."
Idempotente: si la cotización ya estaba `aceptada`, devuelve la orden existente sin crear otra.
Docstring: se usa solo después de que el cliente respondió; NO se usa en el mismo mensaje en que se informó la cotización.

**5. `derivar_a_humano(motivo, consulta_original, id_cotizacion="")`**
Motivos válidos: `MONTO_REQUIERE_APROBACION`, `SERVICIO_NO_ENCONTRADO`, `FUERA_DE_ALCANCE`, `LIMITE_DE_ITERACIONES`, `ERROR_DE_SISTEMA`. Desconocido se guarda como `OTRO`. Usa `comun.derivar` con `proceso = "cotizacion"` e incluye la cotización y las bitácoras de ese id en `datos_json`.

## Scripts y pruebas

- `scripts/probar_mcp_cotizaciones.py`: como el de citas, por stdio y sin modelo. Recorrido feliz con `frena mal y hace ruido al frenar`, más un monto alto y un servicio no encontrado.
- `tests/test_cotizaciones.py` (pytest sobre `logica.py`, base temporal reiniciada):
  - `frena mal y hace ruido al frenar` devuelve una sola coincidencia: `FRE-01` con 270 (80 + 190).
  - `cambio de embrague y cambio de correa de distribucion` devuelve `EMB-01` y `DIS-01`; armar con ambos da total 2500 y `validar_politica_comercial` devuelve `MONTO_REQUIERE_APROBACION` sin testigo.
  - `aire acondicionado nuevo` devuelve `SERVICIO_NO_ENCONTRADO`.
  - Descuento del 10 %: pasa con `aviso` `DESCUENTO_NO_PERMITIDO` y el total sigue en 270.
  - Un código inexistente en `armar_cotizacion` devuelve error sin crear cotización.
  - Testigo usado dos veces: la segunda devuelve `TESTIGO_INVALIDO`. Un testigo anterior deja de valer cuando se emite uno nuevo.
  - Aceptar crea `OT-0001` y deja `COT-0001` en `aceptada`; repetir no crea otra orden.
  - Rechazar deja la cotización en `rechazada` y no crea orden.
  - Toda respuesta `ok: false` trae `codigo`, `mensaje`, `que_hacer` y `clase`.

## Criterios de aceptación

1. `pytest tests/test_cotizaciones.py` pasa completo y `pytest` de la especificación 01 sigue pasando.
2. `python scripts/probar_mcp_cotizaciones.py` lista exactamente 5 herramientas y el recorrido feliz termina en `OT-0001`.
3. Ningún `print(` a stdout en `app/mcp_cotizaciones`.
4. `datos/` quedó sin cambios.
