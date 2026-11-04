# HITL del proyecto frente al BPMN TO-BE

HITL (*human in the loop*) significa que una persona interviene en un punto del proceso. El chat actual es asincrono: cuando una regla pide una persona, el caso se encola en `cola_excepciones` y el cliente recibe un aviso; el grafo **no se pausa**. LangGraph permite una pausa real con `interrupt()` y `Command(resume=...)`, pero en este proyecto eso esta solo en la demo `app/lcel/hitl_demo.py`, no conectado al chat.

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

## Conclusion honesta

- **En produccion** estan la derivacion a la cola de excepciones, la confirmacion en dos pasos con testigo y la aprobacion como tarea pendiente en la cola. Ninguno de esos flujos pausa el grafo.
- **Solo demo** esta el uso real de `interrupt()` y `Command(resume=...)` en `app/lcel/hitl_demo.py`, con `InMemorySaver` y dos casos (aprueba/rechaza).
- Para llevar el HITL del BPMN a LangGraph en produccion faltaria un checkpointer persistente y una API para que el asesor reanude el hilo; mientras tanto, la cola SQLite es la implementacion real y es la que ejercitan los 14 casos.
