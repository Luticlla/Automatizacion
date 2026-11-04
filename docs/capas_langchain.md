# Las cuatro capas del ecosistema en este proyecto

El proyecto usa las cuatro capas del ecosistema de LangChain, pero no todas con el mismo peso. Esta es la evidencia concreta en el codigo.

## 1. LangChain: componentes y LCEL

**Que aporta.** Modelos, prompts, parsers, herramientas, callbacks y la interfaz `Runnable` que permite componer pasos con `|`.

**Evidencia en el proyecto:**

- `app/llm.py` → `get_llm()` construye el `ChatOpenAI` local (`temperature=0`, `base_url` de `.env`, `api_key="sin-clave"`).
- `app/lcel/cadenas.py` → cadenas LCEL explicitas:
  - `cadena_intencion = PROMPT_INTENCION | get_llm() | StrOutputParser()`.
  - `cadena_resumen_derivacion` usa `RunnablePassthrough.assign` + `RunnableLambda` + prompt + modelo + parser.
- `scripts/demo_lcel.py` → demuestra `.invoke`, `.batch` y `.astream`.
- `app/agentes/orquestador.py` → `StructuredTool.from_function` crea `agente_citas` y `agente_cotizacion` con `return_direct=True`.
- `app/agentes/guardas.py` → envuelve herramientas con `StructuredTool` y las invoca con `ainvoke`.
- `app/agentes/trazas.py` → `Trazas(BaseCallbackHandler)` captura `on_tool_start` y `on_tool_end`.
- `app/agentes/mcp_clientes.py` → `MultiServerMCPClient` adapta las herramientas MCP a herramientas LangChain.

**Que no se usa.** No hay cadenas LCEL conectadas al chat: las cadenas explicitas son demos. El chat usa la interfaz `Runnable` de forma implicita a traves de `create_agent`, las herramientas y los callbacks.

## 2. LangGraph: grafos, checkpointer, recursion e interrupt

**Que aporta.** Ejecucion de grafos con estado, memoria por hilo, limites de iteraciones y pausas para intervencion humana.

**Evidencia en el proyecto:**

- `app/agentes/__init__.py` → `MEMORIA = InMemorySaver()`, el checkpointer compartido.
- `app/agentes/citas.py` y `app/agentes/cotizacion.py` → `create_agent(..., checkpointer=MEMORIA)` y `config` con `configurable.thread_id` (`{hilo_id}:citas` / `{hilo_id}:cotizacion`) y `recursion_limit=12`.
- `app/agentes/orquestador.py` → `create_agent(..., checkpointer=MEMORIA)`, `thread_id = hilo_id` y `recursion_limit=8` (12 si atiende directo un flujo abierto).
- `app/agentes/guardas.py` → captura `GraphRecursionError` y deriva con `LIMITE_DE_ITERACIONES`; reintenta una vez si la salida es invalida.
- `app/lcel/hitl_demo.py` → `StateGraph` real con `evaluar_monto` -> condicional `total > 2000` -> `aprobacion_jefe` con `interrupt()` -> `registrar_decision`, compilado con `InMemorySaver`.
- `scripts/demo_hitl.py` → ejecuta hasta la pausa, muestra el payload del `interrupt` y reanuda con `Command(resume={"aprobado": True})` y `Command(resume={"aprobado": False})`.
- `scripts/exportar_grafos.py` → exporta `get_graph().draw_mermaid()` de orquestador, citas, cotizacion y HITL a `docs/grafos/*.mmd` (y PNG).
- `docs/grafos/sistema.mmd` → flujo completo dibujado a mano: cliente, API, orquestador, seguimiento de flujo abierto, guardas, agentes, MCP, SQLite, cola de excepciones, memoria y trazas.

**Que no se usa.** El `interrupt()` no esta conectado al chat; la atencion humana real sigue siendo la cola `cola_excepciones`. Ver `docs/hitl_vs_bpmn.md`.

## 3. Deep Agents: patron supervisor y subagentes, sin el paquete

**Que aporta el patron.** Un agente supervisor que delega en subagentes especializados, cada uno con su propio conjunto de herramientas y su propio hilo de memoria.

**Evidencia en el proyecto:**

- `app/agentes/orquestador.py` → supervisor con dos herramientas (`agente_citas`, `agente_cotizacion`) y `return_direct=True`; elige el subagente y le pasa la consulta tal cual.
- `app/agentes/citas.py` → subagente con las 5 herramientas del servidor MCP de citas.
- `app/agentes/cotizacion.py` → subagente con las 5 herramientas del servidor MCP de cotizaciones.
- `app/agentes/prompts.py` → prompts con alcance negativo (al menos 3 prohibiciones por agente).
- `app/agentes/guardas.py` → contexto de hilo con `contextvars` para que el subagente sepa en que conversacion esta.
- `scripts/inventario_agentes.py` → genera `docs/inventario_agentes.md` y verifica que `deepagents` no esta instalado.

**Que no se usa.** **No se usa el paquete `deepagents`.** La arquitectura supervisor/subagentes se implementa con `create_agent` y `StructuredTool` de LangChain 1.x. No hay planificador, sistema de archivos virtual ni subagentes dinamicos del paquete; solo el patron. La razon es la regla del proyecto: menos piezas y un modelo local de 4B que necesita herramientas acotadas.

## 4. LangSmith: monitoreo

**Que aporta.** Trazas de las ejecuciones, jerarquia de runs, metadata, tags y comparacion de conversaciones.

**Evidencia en el proyecto:**

- `app/config.py` → carga `.env` con `python-dotenv`; el SDK lee `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` y `LANGSMITH_ENDPOINT`.
- `app/agentes/orquestador.py`, `citas.py` y `cotizacion.py` → `config` con `metadata={"hilo_id": ...}`, `tags=["autonorte", ...]` y `run_name`.
- `scripts/verificar_langsmith.py` → comprueba variables sin imprimir la clave y hace una ejecucion de prueba.
- `docs/langsmith.md` → reproduccion, jerarquia verificada y capturas recomendadas.
- Traza verificada: `01a1a4e6-5ad9-7f50-9eff-c731c6a434b3` en el proyecto `autonorte`, con `autonorte_orquestador` > `tools` > `agente_citas` > `autonorte_citas` > herramientas MCP.

**Que no se usa.** LangSmith no reemplaza `var/trazas.jsonl`; ese archivo local sigue siendo la evidencia que leen `scripts/correr_casos.py` y las pruebas. No hay claves en el codigo: `.env` esta en `.gitignore` y `.env.example` solo tiene marcadores.

## Resumen

| Capa | En el proyecto | Archivos clave | Estado |
| --- | --- | --- | --- |
| LangChain | Componentes, herramientas, callbacks y LCEL | `app/llm.py`, `app/lcel/cadenas.py`, `app/agentes/orquestador.py`, `app/agentes/guardas.py`, `app/agentes/trazas.py` | En produccion (componentes) y demos (LCEL explicito) |
| LangGraph | Grafo compilado, checkpointer, recursion, interrupt | `app/agentes/__init__.py`, `app/agentes/*.py`, `app/lcel/hitl_demo.py`, `docs/grafos/` | Grafo y checkpointer en produccion; `interrupt` solo demo |
| Deep Agents | Patron supervisor/subagentes | `app/agentes/orquestador.py`, `app/agentes/citas.py`, `app/agentes/cotizacion.py` | Patron en produccion; paquete `deepagents` no usado |
| LangSmith | Trazas, metadata, tags, jerarquia | `app/config.py`, `app/agentes/*.py`, `scripts/verificar_langsmith.py`, `docs/langsmith.md` | En produccion si `.env` tiene las variables |
