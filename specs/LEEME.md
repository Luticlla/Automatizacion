# Cómo usar estas especificaciones

Orden de trabajo. Cada especificación es una sesión del agente de código y termina con criterios de aceptación que se pueden comprobar sin modelo (salvo la 03 y la 05).

| Paso | Archivo | Qué produce | Se comprueba con |
| --- | --- | --- | --- |
| 1 | `01_base_y_mcp_citas.md` | Base compartida y servidor MCP de citas | `pytest` y `scripts/probar_mcp_citas.py` |
| 2 | `02_mcp_cotizaciones.md` | Servidor MCP de cotizaciones | `pytest` y `scripts/probar_mcp_cotizaciones.py` |
| 3 | `03_agentes_y_orquestador.md` | Modelo, agentes, orquestador y guardas | un script corto que escribe en consola |
| 4 | `04_api_y_chat_web.md` | API FastAPI y página del chat con panel lateral | abrir `http://127.0.0.1:8000` |
| 5 | `05_pruebas_y_evidencias.md` | Casos del chat, evidencias y trazabilidad | `python scripts/correr_casos.py` |

## Prompt para pegar en el agente de código (cada vez)

> Lee `AGENTS.md` y luego `specs/NOMBRE_DE_LA_ESPECIFICACION.md`. Implementa solo lo que pide esa especificación, en las rutas indicadas. Al terminar, ejecuta los criterios de aceptación y muéstrame el resultado de cada uno. Si algo de la especificación contradice un archivo de `datos/`, gana `datos/` y avísame. No agregues funciones que no estén pedidas.

Cambia `NOMBRE_DE_LA_ESPECIFICACION` por el archivo del paso (por ejemplo `01_base_y_mcp_citas`).

## Antes de empezar

- El archivo `.env` necesita una línea más: `HOY_FIJO=2026-10-16`. El resto de las variables ya están.
- Descomprime este contenido dentro de `Automatizacion_Proceso/` (quedan `AGENTS.md` y la carpeta `specs/` junto a `datos/` e `IA_Local/`).
- Si tu IDE no lee `AGENTS.md` solo, pégalo como primer mensaje.
- La API de LangChain y LangGraph cambia entre versiones. Pide al agente que verifique las firmas con la versión instalada (`pip show`, `help()`), sin asumirlas de memoria.

## Si algo falla

- El agente cambia datos o reglas por su cuenta: recuérdale "gana `datos/`".
- El agente agrega piezas que no pediste: pídele que las quite y vuelva a la especificación.
- El modelo de 4B se equivoca en un caso: no subas el tamaño del prompt; ajusta el docstring de la herramienta o el `que_hacer` del error, que es lo que el modelo lee.
