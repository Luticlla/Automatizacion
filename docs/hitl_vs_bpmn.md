# HITL del proyecto frente al BPMN TO-BE

HITL (*human in the loop*) significa que una persona interviene en un punto del proceso. El chat actual es asincrono: cuando una regla pide una persona, el caso se encola en `cola_excepciones` y el cliente recibe un aviso; el grafo **no se pausa**. LangGraph permite una pausa real con `interrupt()` y `Command(resume=...)`; en este proyecto eso esta en la demo `app/lcel/hitl_demo.py` y en el grafo determinista `app/grafo_proceso1.py`, ninguno conectado al chat.

## Puntos HITL que existen hoy

### 1. Derivacion a una persona y cola de excepciones

- **Produccion.** `derivar_a_humano` de `app/mcp_citas/server.py:69` y `app/mcp_cotizaciones/server.py:60` llama a `comun.derivar` (`app/comun.py:83`), que inserta en la tabla `cola_excepciones` con id `EXC-0001`, motivo, consulta original, datos y estado `pendiente`. La API expone esa cola en el panel lateral de tareas (`app/api/main.py`). Motivos usados: `POSIBLE_CORRECTIVO`, `SIN_KIT`, `REQUIERE_APROBACION`, `MONTO_REQUIERE_APROBACION`, `FUERA_DE_ALCANCE`, `LIMITE_DE_ITERACIONES`, `ERROR_DE_SISTEMA`.
- **Equivalente LangGraph.** Un nodo con `interrupt({"motivo": ..., "consulta": ...})` en el punto donde la regla detecta la intervencion humana; el asesor reanudaria con `Command(resume={"decision": ...})`.
- **Compatibilidad.** Conceptualmente compatible, pero no es lo que esta en produccion. La cola vive en SQLite y sobrevive reinicios; `InMemorySaver` no. Para usar `interrupt()` en produccion haria falta un checkpointer persistente o mantener la cola como mecanismo principal. **Hoy: produccion = cola; `interrupt` = no implementado en el chat.**

### 2. Confirmacion en dos pasos con testigo de un solo uso

- **Produccion.** `preparar_cita` y `validar_politica_comercial` emiten un testigo y lo guardan en SQLite; `confirmar_cita` y `programar_servicio` lo consumen. La guarda de turno (`app/agentes/guardas.py`, `_envolver_emisora`, `_envolver_confirmadora` y `aplicar_guardas`) impide confirmar con un testigo emitido en el mismo turno y devuelve `ESPERAR_CONFIRMACION`. Se prueba en P1-01 y P2-03.
- **Equivalente LangGraph.** Un `interrupt` antes de la herramienta de confirmacion y un `Command(resume={"confirmado": True})` con la respuesta del cliente. El grafo quedaria pausado esperando al cliente.
- **Compatibilidad.** Es compatible como idea, pero la implementacion actual es determinista, vive en SQLite y funciona aunque cada llamada MCP sea un proceso distinto. **Hoy: produccion = testigo; `interrupt` para confirmar el cliente = no implementado.** La demo de HITL solo modela la aprobacion del jefe, no la confirmacion del cliente.

### 3. Aprobacion del jefe de taller

- **Produccion.** `consultar_disponibilidad` devuelve `REQUIERE_APROBACION` cuando la duracion supera 2 horas; `validar_politica_comercial` devuelve `MONTO_REQUIERE_APROBACION` cuando el total supera S/ 2000. En ambos casos la instruccion es llamar a `derivar_a_humano`; la aprobacion en si se hace fuera del chat y el caso queda `pendiente` en la cola. **No existe una accion de aprobar/rechazar en el chat.**
- **Equivalente LangGraph.** La demo `app/lcel/hitl_demo.py` implementa exactamente el patron: `evaluar_monto` -> condicional `total > 2000` -> `aprobacion_jefe` con `interrupt()` -> `registrar_decision`. Se reanuda con `Command(resume={"aprobado": True})` o `Command(resume={"aprobado": False})`; el diagrama esta en `docs/grafos/hitl.mmd`. Resultado probado: aprobado -> `aprobada`; rechazado -> `rechazada`.
- **Compatibilidad.** Compatible y demostrado, pero **solo demo**. No esta conectado al chat ni a la cola real.

## Comparacion con el carril Humano del BPMN TO-BE

El identificador `H4a` no aparece en las especificaciones del repositorio; se asocia aqui a la compuerta `G6` / tarea `S_apr` de aprobacion por duracion, segun el pedido.

| Elemento del BPMN (carril Humano) | Como lo implementa hoy el proyecto | Equivalente en LangGraph | Compatible | Estado real |
| --- | --- | --- | --- | --- |
| `S_rev` Revision del asesor por posible correctivo | `derivar_a_humano` con motivo `POSIBLE_CORRECTIVO`; inserta en `cola_excepciones` y el panel muestra la tarea | `interrupt()` en el nodo de clasificacion; reanudar con `Command(resume={"decision": ...})` | Si, conceptualmente | Produccion: derivacion y cola. `interrupt`: no implementado |
| `S_kit` Pedido del kit cuando no hay stock | `derivar_a_humano` con motivo `SIN_KIT`; el asesor gestiona el pedido fuera del chat | `interrupt()` despues de `SIN_KIT`; reanudar cuando el kit este disponible | Si, conceptualmente | Produccion: derivacion y cola. `interrupt`: no implementado |
| `G6` / `S_apr` / `H4a` Aprobacion del jefe de taller | `REQUIERE_APROBACION` (duracion > 2 h) y `MONTO_REQUIERE_APROBACION` (total > S/ 2000) derivan a la cola; no hay boton de aprobar | `aprobacion_jefe` con `interrupt()` y `Command(resume={"aprobado": true/false})`, como en `hitl_demo.py` | Si, y ya esta demostrado | Produccion: solo cola. Aprobacion con `interrupt`: demo aislada |
| `S13f` Cola de fallidos por error de sistema | `guardas.ejecutar` captura `GraphRecursionError` y salidas invalidas; llama a `derivar_a_humano` con `LIMITE_DE_ITERACIONES` o `ERROR_DE_SISTEMA`; queda en la cola | Un nodo de fallback con `interrupt()` o la misma cola; `Command(resume=...)` si se quiere decision humana | Si, pero la cola ya resuelve el caso | Produccion: cola. `interrupt`: no implementado |

## Otros puntos HITL fuera del carril Humano

| Punto | Implementacion actual | Equivalente LangGraph | Estado |
| --- | --- | --- | --- |
| Confirmacion del cliente antes de registrar cita u orden | Testigo de un solo uso + guarda de turno (`ESPERAR_CONFIRMACION`) | `interrupt()` + `Command(resume={"confirmado": true})` | Produccion: testigo. `interrupt`: no implementado |
| Limite de iteraciones del agente | `recursion_limit` en codigo y derivacion automatica | Nodo de fallback con `interrupt()` o derivacion | Produccion: derivacion |

## Grafo determinista del proceso 1

`app/grafo_proceso1.py` modela el TO-BE con un `StateGraph` determinista. No llama al modelo: cada nodo ejecuta codigo y reutiliza las funciones puras de `app/mcp_citas/logica.py`. Los cuatro nodos del carril Humano usan `interrupt()` y se reanudan con `Command(resume=...)`; el checkpointer es `InMemorySaver`.

| Elemento del BPMN | Nodo LangGraph | Que guarda o devuelve |
| --- | --- | --- |
| `Start_1` | `s1v_validar` | `validacion`, `clave` |
| `G1` | `g1_contrato` | `ruta_g1` |
| `S2c` | `s2c_registrar_cola` | `datos_invalidos`, `excepcion_id` |
| `H1r` | `h1r_corregir` | `interrupt`; al reanudar, `devuelta_para_correccion` |
| `S3n` | `s3n_normalizar` | `clave` |
| `S2b` | `s2b_consultar_clave` | `estado_validacion` |
| `G2` | `g2_clave_existe` | `ruta_g2` |
| `S4d` | `s4d_devolver` | `ya_existe`, `cita` |
| `S5c` | `s5c_clasificar` | `estado_validacion` |
| `G3` | `g3_preventivo` | `ruta_g3` |
| `S_rev` | `s_rev_encolar` | `excepcion_id` con motivo `POSIBLE_CORRECTIVO` |
| `H2d` | `h2d_resolver` | `interrupt`; al reanudar, `resolucion` (`correctivo` o `preventivo`) |
| `G3c` | `g3c_resolucion` | `ruta_g3c` |
| `S6d` | `s6d_notificar` | `derivado_correctivo` |
| `G3b` | `g3b_continuar` | Ruta al paralelo |
| `AND1` / `AND2` | `and1` / `and2` | Abren y cierran las ramas paralelas |
| `S7c` | `s7c_consultar_cupo` | `consulta_cupo` |
| `S8k` | `s8k_verificar_kit` | `consulta_kit` |
| `G4` | `g4_clasificar` | `ruta_g4` |
| `S_kit` | `s_kit_encolar` | `excepcion_id` con motivo `SIN_KIT` |
| `H3k` | `h3k_gestionar` | `interrupt`; al reanudar, `kit_gestionado` |
| `S9q` / `S9a` | `s9q_alternativas` / `s9a_proponer` | `alternativas` y texto para el cliente |
| `G5` | `g5_eleccion` | Ruta a `IC_msg`; el plazo de 24 h queda aislado |
| `IC_msg` | `ic_msg` | `interrupt`; al reanudar, `fecha_elegida` y nueva validacion |
| `IC_t24` | `ic_t24` | Nodo aislado: temporizador de 24 h no implementado |
| `S10d` | `s10d_desistida` | `desistida` |
| `G4b` | `g4b_continuar` | Ruta a `G6` |
| `G6` | `g6_duracion` | `ruta_g6` |
| `S_apr` | `s_apr_encolar` | `excepcion_id` con motivo `REQUIERE_APROBACION` |
| `H4a` | `h4a_aprobar` | `interrupt`; al reanudar, `aprobacion` |
| `G6b` | `g6b_decision` | `ruta_g6b` |
| `S12r` | `s12r_registrar` | `cita` o el error de `preparar_cita` / `confirmar_cita` |
| `S14c` | `s14c_confirmar` | `confirmada` con `id_cita` |
| `End_1` a `End_7` | `end_1` a `end_7` | Cierre de cada ruta |
| `BE_cupo`, `BE_kit`, `BE_alt`, `BE_err`, `BT_kit`, `H5r`, `S_cls`, `S13f` | `be_cupo`, `be_kit`, `be_alt`, `be_err`, `bt_kit`, `h5r_reprogramar`, `s_cls`, `s13f_cola_fallidos` | Nodos aislados: errores, reintentos y plazos no implementados |

### Decisiones honestas del grafo

- `S7c` y `S8k` se ejecutan en paralelo real, pero `logica.py` expone una sola funcion combinada (`consultar_disponibilidad`); ambas ramas la invocan y `G4` usa el resultado comun. El diagrama conserva la topologia `AND1 -> S7c/S8k -> AND2`.
- `H3k` termina en `kit_gestionado`: el stock de `preventivo_5000` sigue en 0 y `logica.py` no tiene una accion para actualizarlo. El grafo no inventa esa escritura.
- `H4a` aprobado intenta `S12r`, pero `preparar_cita` vuelve a devolver `REQUIERE_APROBACION` porque la regla de duracion no tiene excepcion en `logica.py`. El caso termina sin cita y con el error visible.
- `H4a` rechazado termina en `end_4` (`rechazada_por_jefe`): el BPMN no define una compuerta de rechazo, asi que el grafo cierra el caso sin registrar.
- `IC_t24`, los cuatro `BE_*`, `BT_kit`, `H5r`, `S_cls` y `S13f` quedan como nodos aislados; no se simulan temporizadores, reintentos ni la cola de fallidos.

### Como se ejecuta

```bash
.venv/bin/python scripts/demo_grafo.py
.venv/bin/python -m pytest tests/test_grafo_proceso1.py -q
```

La demo corre cinco escenarios: cita nueva, datos invalidos, posible correctivo, sin kit y duracion mayor a 2 horas. Genera `docs/grafos/proceso1.mmd` y `docs/grafos/proceso1.png`.

## Conclusion honesta

- **En produccion** estan la derivacion a la cola de excepciones, la confirmacion en dos pasos con testigo y la aprobacion como tarea pendiente en la cola. Ninguno de esos flujos pausa el grafo.
- **En demos LangGraph** esta el uso real de `interrupt()` y `Command(resume=...)`: `app/lcel/hitl_demo.py` (aprueba/rechaza) y `app/grafo_proceso1.py` (H1r, H2d, H3k, H4a e IC_msg), ambos con `InMemorySaver`.
- Para llevar el HITL del BPMN a LangGraph en produccion faltaria un checkpointer persistente y una API para que el asesor reanude el hilo; mientras tanto, la cola SQLite es la implementacion real y es la que ejercitan los 14 casos.
