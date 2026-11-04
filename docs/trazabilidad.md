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

## Grafo determinista del proceso 1 (TO-BE)

| Elemento del BPMN | Nodo LangGraph | Archivo y función | Verificación |
| --- | --- | --- | --- |
| `Start_1`, `S1v`, `G1` | `s1v_validar`, `g1_contrato` | `app/grafo_proceso1.py` → `s1v_validar` / `g1_contrato` | `test_flujo_feliz...`, `test_datos_invalidos...` |
| `S2c`, `H1r` | `s2c_registrar_cola`, `h1r_corregir` | `app/grafo_proceso1.py` → `s2c_registrar_cola` / `h1r_corregir` | `test_datos_invalidos_pausan_en_h1r` |
| `S3n`, `S2b`, `G2`, `S4d` | `s3n_normalizar`, `s2b_consultar_clave`, `g2_clave_existe`, `s4d_devolver` | `app/grafo_proceso1.py` | `test_cita_existente_no_duplica` |
| `S5c`, `G3`, `S_rev`, `H2d`, `G3c`, `S6d` | `s5c_clasificar`, `g3_preventivo`, `s_rev_encolar`, `h2d_resolver`, `g3c_resolucion`, `s6d_notificar` | `app/grafo_proceso1.py` | `test_posible_correctivo...`, `test_h2d_puede_devolver...` |
| `AND1`, `S7c`, `S8k`, `AND2`, `G4` | `and1`, `s7c_consultar_cupo`, `s8k_verificar_kit`, `and2`, `g4_clasificar` | `app/grafo_proceso1.py` | `test_flujo_feliz...` |
| `S_kit`, `H3k` | `s_kit_encolar`, `h3k_gestionar` | `app/grafo_proceso1.py` | `test_sin_kit_pausa_en_h3k...` |
| `S9q`, `S9a`, `G5`, `IC_msg` | `s9q_alternativas`, `s9a_proponer`, `g5_eleccion`, `ic_msg` | `app/grafo_proceso1.py` | `test_sin_cupo_ofrece_alternativas...` |
| `G4b`, `G6`, `S_apr`, `H4a`, `G6b` | `g4b_continuar`, `g6_duracion`, `s_apr_encolar`, `h4a_aprobar`, `g6b_decision` | `app/grafo_proceso1.py` | `test_duracion_larga...`, `test_h4a_rechazado...` |
| `S12r`, `S14c` | `s12r_registrar`, `s14c_confirmar` | `app/grafo_proceso1.py` | `test_flujo_feliz...` |
| `End_1` a `End_7` | `end_1` a `end_7` | `app/grafo_proceso1.py` | `test_grafo_expone_nodos_bpmn...` |
| `IC_t24`, `BE_cupo`, `BE_kit`, `BE_alt`, `BE_err`, `BT_kit`, `H5r`, `S_cls`, `S13f` | `ic_t24`, `be_cupo`, `be_kit`, `be_alt`, `be_err`, `bt_kit`, `h5r_reprogramar`, `s_cls`, `s13f_cola_fallidos` | `app/grafo_proceso1.py` | Nodos aislados: no implementados |

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
| `app/grafo_proceso1.py` | Grafo determinista del TO-BE del proceso 1, con HITL y ramas paralelas | Proceso 1 / LangGraph | `tests/test_grafo_proceso1.py` |
| `scripts/demo_grafo.py` | Corre 5 escenarios del grafo y exporta el diagrama | Proceso 1 / LangGraph | ejecución manual |
| `tests/test_grafo_proceso1.py` | Pruebas del grafo sin modelo | Proceso 1 | `pytest -q` |
| `docs/grafos/proceso1.mmd` | Diagrama Mermaid del grafo del proceso 1 | Proceso 1 | `scripts/demo_grafo.py` |
| `docs/grafos/proceso1.png` | Imagen del grafo del proceso 1 | Proceso 1 | `scripts/demo_grafo.py` |
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
| `evidencias/2026-11-03_2355_pytest.txt` | Salida de `pytest` (33 passed) | Cierre de la sesión anterior | `pytest -q` |
| `evidencias/2026-11-03_2355_consola_casos.txt` | Salida de los 14 casos | Cierre de la sesión anterior | `scripts/correr_casos.py` |
| `evidencias/2026-11-03_2357_resultados.md` | Evidencia detallada de los 14 casos | Cierre de la sesión anterior | `scripts/correr_casos.py` |
| `evidencias/2026-11-04_0044_pytest.txt` | Salida de `pytest` (43 passed) | Grafo y pruebas | `pytest -q` |
| `evidencias/2026-11-04_0044_demo_grafo.txt` | Salida de los 5 escenarios del grafo | Grafo / HITL | `scripts/demo_grafo.py` |
| `evidencias/2026-11-04_0046_consola_casos.txt` | Salida de los 14 casos con el modelo local | Regresión del chat | `scripts/correr_casos.py` |
| `evidencias/2026-11-04_0046_resultados.md` | Evidencia detallada: 14 de 14 casos | Regresión del chat | `scripts/correr_casos.py` |

## Archivos modificados en la sesión

| Archivo | Cambio | Verificación |
| --- | --- | --- |
| `app/agentes/orquestador.py` | `metadata`, `tags` y `run_name` en `responder` | traza LangSmith anidada |
| `app/agentes/citas.py` | `metadata`, `tags` y `run_name` en `consultar` | traza LangSmith anidada |
| `app/agentes/cotizacion.py` | `metadata`, `tags` y `run_name` en `consultar` | traza LangSmith anidada |
| `.env.example` | `LANGSMITH_TRACING=false` y se elimino `API_LANGSMITH` | `.env` sigue en `.gitignore` |
| `.env` (ignorado) | `HOY_FIJO=2026-10-16` y variables `LANGSMITH_*` | no se versiona; `.env.example` tiene marcadores |
