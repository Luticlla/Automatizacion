# LCEL en el proyecto

LCEL (LangChain Expression Language) es la forma de componer pasos con el operador `|`. Cada paso es un `Runnable` y el resultado de la composicion es un `RunnableSequence` que expone `invoke`, `batch` y `astream` (y sus versiones asincronas). En este proyecto las cadenas LCEL explicitas viven en `app/lcel/cadenas.py` y son demos: **no estan conectadas al chat**. El chat usa la misma interfaz `Runnable` de forma implicita a traves de los agentes, las herramientas y los callbacks.

## Cadenas explicitas (nuevas)

| Termino | Archivo y linea | Que hace |
| --- | --- | --- |
| `ChatPromptTemplate.from_messages` | `app/lcel/cadenas.py:8` y `app/lcel/cadenas.py:32` | Arma el prompt con mensajes de sistema y de usuario y deja variables (`{mensaje}`, `{motivo}`, etc.) que se rellenan al invocar. |
| Operador `\|` (composicion) | `app/lcel/cadenas.py:19` y `app/lcel/cadenas.py:41`-`46` | Encadena prompt, modelo y parser en un `RunnableSequence`; la salida de cada paso entra al siguiente. |
| `RunnableSequence` | `app/lcel/cadenas.py:19` y `app/lcel/cadenas.py:41` | Es el tipo de objeto que produce el operador `\|`; por eso `cadena_intencion` y `cadena_resumen_derivacion` se pueden invocar igual que cualquier `Runnable`. |
| `get_llm()` / `ChatOpenAI` | `app/llm.py:8`-`15`, usado en `app/lcel/cadenas.py:19` y `app/lcel/cadenas.py:45` | Devuelve el modelo local como `ChatOpenAI`, que es un `Runnable` y acepta un prompt o una lista de mensajes. |
| `StrOutputParser` | `app/lcel/cadenas.py:2`, `app/lcel/cadenas.py:19` y `app/lcel/cadenas.py:46` | Convierte la respuesta del modelo (`AIMessage`) en texto plano. |
| `RunnablePassthrough.assign` | `app/lcel/cadenas.py:42` | Copia la entrada y le agrega el campo `contexto` sin perder los datos originales de la derivacion. |
| `RunnableLambda` | `app/lcel/cadenas.py:42` y `app/lcel/cadenas.py:43` | Envuelve una funcion normal (`_contexto_derivacion` y la seleccion del campo `contexto`) para que se comporte como `Runnable`. |
| `.invoke` | `scripts/demo_lcel.py:45` y `scripts/demo_lcel.py:57` | Ejecuta una cadena con una sola entrada y devuelve una sola salida. |
| `.batch` | `scripts/demo_lcel.py:49` | Ejecuta la cadena con una lista de entradas y devuelve la lista de salidas. |
| `.astream` | `scripts/demo_lcel.py:37` | Ejecuta la cadena de forma asincrona y entrega la salida por trozos a medida que se produce. |

## Terminos implicitos en el chat

| Termino | Archivo y linea | Que hace |
| --- | --- | --- |
| Interfaz `Runnable` con `ainvoke` | `app/agentes/citas.py:26`, `app/agentes/cotizacion.py:26` y `app/agentes/guardas.py:204`, `215`, `259` | Cada agente y cada herramienta se invocan con `ainvoke`, que es el metodo asincrono comun de todo `Runnable`. |
| `create_agent` como `Runnable` compilado | `app/agentes/citas.py:14`, `app/agentes/cotizacion.py:14` y `app/agentes/orquestador.py:64` | `create_agent` devuelve un grafo compilado que cumple la interfaz `Runnable`; por eso se le pasa a `ainvoke` y acepta `config`. |
| `StructuredTool` | `app/agentes/orquestador.py:27`, `app/agentes/orquestador.py:37` y `app/agentes/guardas.py:141`, `161`, `176` | Convierte funciones Python en herramientas con nombre, descripcion, esquema de argumentos y `return_direct`; tambien son `Runnable`. |
| `RunnableConfig` con `configurable` | `app/agentes/citas.py:29`, `app/agentes/cotizacion.py:29` y `app/agentes/orquestador.py:97` | El diccionario `config` transporta valores por ejecucion; `configurable.thread_id` selecciona el hilo de memoria del checkpointer. |
| `recursion_limit` | `app/agentes/citas.py:30`, `app/agentes/cotizacion.py:30` y `app/agentes/orquestador.py:98` | Limita la cantidad de pasos del grafo para cortar bucles del modelo; al agotarse se deriva a una persona. |
| `callbacks` | `app/agentes/orquestador.py:99` | Pasa el callback de trazas a la invocacion del orquestador para registrar herramientas y respuestas. |
| `metadata` | `app/agentes/citas.py:31`, `app/agentes/cotizacion.py:31` y `app/agentes/orquestador.py:100` | Adjunta el `hilo_id` a la traza de LangSmith para poder buscar la conversacion. |
| `tags` | `app/agentes/citas.py:32`, `app/agentes/cotizacion.py:32` y `app/agentes/orquestador.py:101` | Etiqueta cada ejecucion con `autonorte` y el nombre del agente para filtrar en LangSmith. |
| `run_name` | `app/agentes/citas.py:33`, `app/agentes/cotizacion.py:33` y `app/agentes/orquestador.py:102` | Da un nombre legible a la ejecucion en LangSmith (`autonorte_citas`, `autonorte_cotizacion`, `autonorte_orquestador`). |
| `BaseCallbackHandler` | `app/agentes/trazas.py:5` y `app/agentes/trazas.py:93` | Clase base de LangChain que recibe eventos (`on_tool_start`, `on_tool_end`, etc.); `Trazas` la hereda para escribir `var/trazas.jsonl`. |
| `ChatOpenAI` como `Runnable` | `app/llm.py:15` | El modelo local se comporta como cualquier otro `Runnable`: acepta prompts, mensajes y `config`. |

`RunnableParallel` no se usa en el proyecto: la composicion de varios campos se resuelve con `RunnablePassthrough.assign`, que es la alternativa equivalente para este caso.
