# Trazabilidad con el BPMN

Cada fila liga un elemento del BPMN con la herramienta o el agente que lo implementa, su archivo y su función, y el caso de `scripts/correr_casos.py` que lo ejercita.

## Proceso 1 — Cita de mantenimiento preventivo (TO-BE)

| Elemento del BPMN | Herramienta o agente | Archivo y función | Caso de prueba |
| --- | --- | --- | --- |
| S1v Validar la solicitud contra el contrato de datos / G1 | `validar_solicitud` (errores `datos`) | `app/mcp_citas/logica.py` → `validar_solicitud` | P1-06 |
| S3n Normalizar y calcular la clave | `validar_solicitud` (devuelve la clave) | `app/mcp_citas/logica.py` → `validar_solicitud` / `calcular_clave` | P1-01 |
| S2b Consultar la clave / G2 / S4d Devolver la cita ya registrada | `validar_solicitud` (estado `ya_existe`) | `app/mcp_citas/logica.py` → `validar_solicitud` | P1-02 |
| S5c Clasificar el servicio / G3 | `validar_solicitud` (estado `posible_falla`) | `app/mcp_citas/logica.py` → `validar_solicitud` | P1-07 |
| S_rev Encolar para revisión del asesor | `derivar_a_humano` (POSIBLE_CORRECTIVO) | `app/mcp_citas/logica.py` → `derivar_a_humano` | P1-07 |
| S7c Consultar disponibilidad / S8k Verificar kit / G4 | `consultar_disponibilidad` | `app/mcp_citas/logica.py` → `consultar_disponibilidad` / `_verificar_disponibilidad` | P1-04 |
| S_kit Encolar pedido del kit | `derivar_a_humano` (SIN_KIT) | `app/mcp_citas/logica.py` → `derivar_a_humano` | P1-04 |
| S9q / S9a Tres fechas alternativas | `consultar_disponibilidad` (SIN_CUPO con alternativas) | `app/mcp_citas/logica.py` → `_alternativas` | P1-03 |
| G6 Duración mayor a 2 h / S_apr Encolar aprobación | `consultar_disponibilidad` + `derivar_a_humano` (REQUIERE_APROBACION) | `app/mcp_citas/logica.py` → `_verificar_disponibilidad` + `derivar_a_humano` | P1-05 |
| S12r Registrar la cita con unicidad | `preparar_cita` + `confirmar_cita` (testigo de un solo uso; clave única en SQLite) | `app/mcp_citas/logica.py` → `preparar_cita` / `confirmar_cita` | P1-01 |
| S_cls Clasificar el error y su clase | Campo `clase` en todo error | `app/comun.py` → `error` | P1-06 |
| S13f Cola de fallidos | `derivar_a_humano` (cola de excepciones) | `app/comun.py` → `derivar` | P1-04 |
| S14c Enviar la confirmación inmediata | Respuesta del agente tras `confirmar_cita` | `app/agentes/citas.py` → `consultar` | P1-01 |
| Proc_Cliente (pool Cliente) | El chat web | `app/web/index.html` | P1-01 a P2-06 (todos) |

## Proceso 2 — Cotización de reparación correctiva

| Elemento del BPMN | Herramienta o agente | Archivo y función | Caso de prueba |
| --- | --- | --- | --- |
| completar con el TO-BE de cotización | `consultar_tarifario` | `app/mcp_cotizaciones/logica.py` → `consultar_tarifario` | P2-01, P2-04, P2-05 |
| completar con el TO-BE de cotización | `armar_cotizacion` | `app/mcp_cotizaciones/logica.py` → `armar_cotizacion` | P2-01, P2-04 |
| completar con el TO-BE de cotización | `validar_politica_comercial` | `app/mcp_cotizaciones/logica.py` → `validar_politica_comercial` | P2-01, P2-02, P2-04 |
| completar con el TO-BE de cotización | `programar_servicio` | `app/mcp_cotizaciones/logica.py` → `programar_servicio` | P2-03 |
| completar con el TO-BE de cotización | `derivar_a_humano` (cotización) | `app/mcp_cotizaciones/logica.py` → `derivar_a_humano` | P2-04 |

## Orquestador, agentes y guardas (patrones S05)

| Elemento del BPMN | Herramienta o agente | Archivo y función | Caso de prueba |
| --- | --- | --- | --- |
| Decisión de ruta del chat | Orquestador (elige agente con `return_direct=True`) | `app/agentes/orquestador.py` → `responder` | P2-06 |
| Agente citas | Agente de citas (5 herramientas MCP) | `app/agentes/citas.py` → `consultar` | P1-01 a P1-08 |
| Agente cotización | Agente de cotización (5 herramientas MCP) | `app/agentes/cotizacion.py` → `consultar` | P2-01 a P2-05 |
| Patrón S05 5: guarda de turno | Testigo emitido en el turno no se puede usar en el mismo turno | `app/agentes/guardas.py` → `aplicar_guardas` | P1-01, P2-03 |
| Seguimiento del hilo entre turnos (spec 03) | Guarda del "flujo activo": último agente por hilo, línea al inicio del mensaje del sistema del orquestador | `app/agentes/guardas.py` → `ultimo_agente` / `app/agentes/orquestador.py` → `_flujo_activo` | P2-03 |
| Enrutamiento de seguimiento determinista | Flujo abierto por hilo: la continuación va directo al mismo agente; "cotiz"/"cita" del otro tema decide el orquestador | `app/agentes/guardas.py` → `flujo_abierto` / `app/agentes/orquestador.py` → `_seguimiento` / `responder` | P1-01, P2-01 a P2-03 |
| Patrón S05 7: límite de iteraciones | `recursion_limit` en código; si se agota, deriva con LIMITE_DE_ITERACIONES | `app/agentes/orquestador.py` → `responder` / `app/agentes/guardas.py` → `ejecutar` | P1-01 a P2-06 (todas las invocaciones) |
| Salida inválida (spec 03) | Reintento y derivación con ERROR_DE_SISTEMA | `app/agentes/guardas.py` → `ejecutar` / `_salida_valida` | P1-01 a P2-06 (todas las invocaciones) |
| Modelo apagado (spec 03) | Mensaje claro sin excepción | `app/agentes/orquestador.py` → `responder` / `app/llm.py` → `comprobar_modelo` | `pytest` `tests/test_guardas.py::test_modelo_apagado_responde_sin_traceback` |

## Archivos nuevos de la sesión (LCEL, LangGraph, LangSmith, agentes y capas)

| Archivo nuevo | Contenido | Relación con el proceso o patrón | Verificación |
| --- | --- | --- | --- |
| `.env.example` | Variables de entorno sin claves reales, incluidas `LANGSMITH_*` | Configuración reproducible; `.env` sigue en `.gitignore` | `git check-ignore .env` |
| `requirements.txt` | Versiones exactas de las librerías instaladas | Reproducción del entorno | `pip freeze` |
| `app/lcel/__init__.py` | Paquete de demos LCEL | LCEL | importación |
| `app/lcel/cadenas.py` | `cadena_intencion` y `cadena_resumen_derivacion` | LCEL explícito | `scripts/demo_lcel.py` |
| `app/lcel/hitl_demo.py` | `StateGraph` con `interrupt()` y `InMemorySaver` | HITL / G6-S_apr | `scripts/demo_hitl.py` |
| `scripts/demo_lcel.py` | `.invoke`, `.batch` y `.astream` sobre 3 mensajes | LCEL | ejecución manual |
| `scripts/exportar_grafos.py` | Exporta `get_graph().draw_mermaid()` y PNG | LangGraph | `docs/grafos/` |
| `scripts/demo_hitl.py` | Pausa el grafo y reanuda con `Command(resume=...)` | HITL | ejecución manual |
| `scripts/verificar_langsmith.py` | Comprueba variables sin imprimir la clave y ejecuta una prueba | LangSmith | ejecución manual |
| `scripts/inventario_agentes.py` | Lee el código y genera el inventario | Supervisor y subagentes | `docs/inventario_agentes.md` |
| `docs/lcel.md` | Términos LCEL con archivo y línea | LCEL | revisión |
| `docs/hitl_vs_bpmn.md` | Comparación HITL vs BPMN TO-BE | HITL | revisión |
| `docs/langsmith.md` | Pasos de reproducción y capturas | LangSmith | revisión |
| `docs/inventario_agentes.md` | Inventario de los 3 agentes | Supervisor y subagentes | regenerable |
| `docs/capas_langchain.md` | Las cuatro capas del ecosistema | LangChain, LangGraph, Deep Agents y LangSmith | revisión |
| `docs/grafos/sistema.mmd` | Flujo completo dibujado a mano | Todos los procesos | revisión |
| `docs/grafos/orquestador.mmd` | Grafo del orquestador | Orquestador | `scripts/exportar_grafos.py` |
| `docs/grafos/orquestador.png` | Imagen del grafo del orquestador | Orquestador | `scripts/exportar_grafos.py` |
| `docs/grafos/citas.mmd` | Grafo del agente de citas | Agente de citas | `scripts/exportar_grafos.py` |
| `docs/grafos/citas.png` | Imagen del grafo del agente de citas | Agente de citas | `scripts/exportar_grafos.py` |
| `docs/grafos/cotizacion.mmd` | Grafo del agente de cotización | Agente de cotización | `scripts/exportar_grafos.py` |
| `docs/grafos/cotizacion.png` | Imagen del grafo del agente de cotización | Agente de cotización | `scripts/exportar_grafos.py` |
| `docs/grafos/hitl.mmd` | Grafo de la demo HITL | HITL | `scripts/demo_hitl.py` |
| `docs/grafos/hitl.png` | Imagen del grafo HITL | HITL | `scripts/demo_hitl.py` |
| `evidencias/2026-11-03_2355_pytest.txt` | Salida de `pytest` (33 passed) | Cierre | `pytest -q` |
| `evidencias/2026-11-03_2355_consola_casos.txt` | Salida de los 14 casos | Cierre | `scripts/correr_casos.py` |
| `evidencias/2026-11-03_2357_resultados.md` | Evidencia detallada de los 14 casos | Cierre | `scripts/correr_casos.py` |

## Archivos modificados en la sesión

| Archivo | Cambio | Verificación |
| --- | --- | --- |
| `app/agentes/orquestador.py` | `metadata`, `tags` y `run_name` en `responder` | traza LangSmith anidada |
| `app/agentes/citas.py` | `metadata`, `tags` y `run_name` en `consultar` | traza LangSmith anidada |
| `app/agentes/cotizacion.py` | `metadata`, `tags` y `run_name` en `consultar` | traza LangSmith anidada |
| `.env` (ignorado) | `HOY_FIJO=2026-10-16` y variables `LANGSMITH_*` | no se versiona; `.env.example` tiene marcadores |
