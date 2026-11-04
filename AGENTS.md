# AGENTS.md — Asistente de Autonorte (chat web con agentes)

Lee este archivo completo antes de escribir código. Las especificaciones de cada módulo están en `specs/`. Trabaja **una especificación a la vez**, en el orden de `specs/LEEME.md`, y no pases a la siguiente hasta cumplir los criterios de aceptación de la actual.

## Qué se construye

Un chat web en `http://127.0.0.1:8000` para Autonorte Servicios Automotrices S.A.C. (curso Automatización Inteligente de Procesos, Grupo 4). Atiende dos procesos y nada más:

1. **Cita de mantenimiento preventivo** (valida datos, revisa kit y cupo, pide confirmación, registra).
2. **Cotización de reparación correctiva** (busca en tarifario, arma cotización, valida política, pide confirmación, genera orden de trabajo).

No es una app con pantallas de gestión. Es un chat con un panel lateral de solo lectura (Citas, Tareas pendientes, Cotizaciones).

## Restricciones que no se negocian

- Modelo local pequeño (Qwen3.5-4B por `llama-server`, API compatible con OpenAI en `http://127.0.0.1:8080/v1`). Un modelo de 4B alucina fácil: **el código decide, el modelo solo conversa y elige herramienta**. Cupos, precios, totales, claves, ids y validaciones se calculan en código dentro de las herramientas. El modelo nunca escribe un precio, un id ni una hora por su cuenta.
- Nunca llames a un modelo en la nube. No pongas claves en el código. Todo lo configurable va en `.env`.
- Mantenlo simple. Si dudas entre dos diseños, elige el que tenga menos piezas. No agregues funciones que no estén en la especificación (login, adjuntos, streaming de tokens, reintentos con espera, temporizadores, webhooks).
- Los archivos de `datos/` son semillas de solo lectura. Nunca los modifiques; se cargan a SQLite al iniciar.
- Idioma de los textos al usuario, mensajes de error y comentarios: español. Identificadores de código: ASCII sin tildes.

## Arquitectura (resumen)

```
Chat web (index.html) -> FastAPI -> Orquestador (LLM)
                                      |-- herramienta agente_citas      -> Agente de citas (LLM, 5 herramientas)      -> MCP citas (stdio)         -> var/proceso1.db
                                      |-- herramienta agente_cotizacion -> Agente de cotización (LLM, 5 herramientas) -> MCP cotizaciones (stdio) -> var/proceso2.db
```

- Orquestador: elige el agente y recuerda el hilo. Solo tiene 2 herramientas (los dos agentes), con `return_direct=True`: la respuesta del agente va directo al cliente sin que el orquestador la reescriba.
- Cada agente ve solo las 5 herramientas de su servidor MCP.
- Memoria por hilo con `InMemorySaver` de LangGraph. Cada agente usa su propio hilo: `"{hilo_id}:citas"` y `"{hilo_id}:cotizacion"`.
- La validación comercial (descuento máximo y monto máximo) es una **herramienta determinista**, no un agente con modelo.

## Estructura de carpetas

```
Automatizacion_Proceso/
  AGENTS.md  specs/  datos/  IA_Local/  .env  .venv/
  app/
    config.py            # lee .env
    db.py                # crea y carga las dos bases SQLite desde datos/
    comun.py             # errores, testigos, bitácora, cola de excepciones
    llm.py               # get_llm()
    mcp_citas/    logica.py  server.py
    mcp_cotizaciones/  logica.py  server.py
    agentes/      prompts.py  citas.py  cotizacion.py  orquestador.py  guardas.py  trazas.py
    api/main.py
    web/index.html
  scripts/  reiniciar_datos.py  probar_mcp_citas.py  probar_mcp_cotizaciones.py  correr_casos.py
  tests/
  var/        # bases SQLite y trazas; ignorar en git
  evidencias/ # resultados de las pruebas, con fecha en el nombre
  docs/trazabilidad.md
```

Separa siempre la lógica pura (`logica.py`, sin MCP) de la envoltura MCP (`server.py`). Así se prueba con pytest sin servidor ni modelo.

## Patrones obligatorios (checklist de la sesión S05)

1. **Docstring de cada herramienta** con tres partes breves: qué hace, cuándo usarla y **cuándo NO usarla**. Máximo 5 líneas. El modelo lee esto para elegir.
2. **Errores como diccionario, nunca como excepción**: `{"ok": false, "codigo": "...", "mensaje": "...", "que_hacer": "...", "clase": "datos|transitorio|sistema"}`. El `que_hacer` es una instrucción literal para el agente. Una excepción inesperada se captura, se registra en stderr y se devuelve con `clase: "sistema"` y `que_hacer: "Deriva a una persona"`.
3. **Nunca imprimir en stdout** en un servidor MCP (rompe el protocolo stdio). Logs a stderr o a archivo.
4. **Confirmación en dos pasos con testigo de un solo uso**. La herramienta que prepara emite el testigo y lo guarda en SQLite; la que confirma lo consume. El estado vive en SQLite, nunca en memoria del proceso (cada llamada MCP puede ser un proceso distinto).
5. **Guarda de turno**: una herramienta de confirmación no puede usar un testigo emitido en el mismo turno del cliente. Ver `specs/03`.
6. **Prompt con alcance negativo**: cada prompt de sistema incluye al menos 3 prohibiciones explícitas.
7. **Límite de iteraciones en código** (`recursion_limit`). Si se agota, se deriva a una persona con la consulta, los pasos y el motivo.
8. **Ruta de escalamiento**: `derivar_a_humano` guarda consulta original, datos obtenidos, pasos recorridos y motivo en la cola de excepciones.
9. **`temperature=0`** en todas las llamadas al modelo.
10. **Probar el servidor MCP solo (sin modelo)** antes de conectarlo a un agente.
11. **Máximo 5 herramientas por agente.**

## Reglas del Lab 02 que se aplican

- Contrato de datos de 9 campos validado antes de cualquier acción; se devuelven **todos** los errores a la vez.
- Clave de idempotencia: SHA-256 de `placa|fecha|tipo` normalizados, primeros 32 caracteres hexadecimales. Verificado: `T4M891|2026-09-22|preventivo_10000` produce `1b114e68d6a3241784560e39cf0868d9`.
- Clases de error: `datos` (el cliente debe corregir), `transitorio` (reintentar), `sistema` (derivar).
- Evidencia: al menos un caso exitoso y uno fallido que se corrige y se repite, guardados en `evidencias/`.
- Trazabilidad: cada herramienta y agente se liga a un elemento del BPMN en `docs/trazabilidad.md`.

## Configuración (`.env`)

```
MODEL_BACKEND=llamacpp
MODEL_BASE_URL=http://127.0.0.1:8080/v1
MODEL_NAME=qwen
HOY_FIJO=2026-10-16
```

`HOY_FIJO` fija la fecha "de hoy" para validar fechas y para que las pruebas sean repetibles. Si está vacío, se usa la fecha del sistema.

## Cómo se ejecuta

1. Terminal 1: `cd IA_Local && ./qwen.sh` (el modelo ya está listo; no lo modifiques).
2. Terminal 2: `source .venv/bin/activate && python scripts/reiniciar_datos.py && uvicorn app.api.main:app --port 8000`.
3. Abrir `http://127.0.0.1:8000`.

## Trazabilidad con el BPMN del proceso 1 (TO-BE)

| Elemento BPMN | Implementación |
| --- | --- |
| S1v Validar la solicitud contra el contrato de datos / G1 | `validar_solicitud` (errores `datos`) |
| S3n Normalizar y calcular la clave | `validar_solicitud` (devuelve la clave) |
| S2b Consultar la clave / G2 / S4d Devolver la cita ya registrada | `validar_solicitud` (estado `ya_existe`) |
| S5c Clasificar el servicio / G3 | `validar_solicitud` (estado `posible_falla`) |
| S_rev Encolar para revisión del asesor | `derivar_a_humano` (POSIBLE_CORRECTIVO) |
| S7c Consultar disponibilidad / S8k Verificar kit / G4 | `consultar_disponibilidad` |
| S_kit Encolar pedido del kit | `derivar_a_humano` (SIN_KIT) |
| S9q / S9a Tres fechas alternativas | `consultar_disponibilidad` (SIN_CUPO con alternativas) |
| G6 Duración mayor a 2 h / S_apr Encolar aprobación | `consultar_disponibilidad` + `derivar_a_humano` (REQUIERE_APROBACION) |
| S12r Registrar la cita con unicidad | `confirmar_cita` (clave única en SQLite) |
| S_cls Clasificar el error y su clase | campo `clase` en todo error |
| S13f Cola de fallidos | `derivar_a_humano` (clase sistema) |
| S14c Enviar la confirmación inmediata | respuesta del agente tras `confirmar_cita` |
| Proc_Cliente (pool Cliente) | el chat web |

Para el proceso 2 se liga cada herramienta al elemento del TO-BE de cotización (completar en `docs/trazabilidad.md`).
