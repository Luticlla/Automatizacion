# LangSmith en el proyecto

LangSmith se activa **solo con variables de entorno**. No hay claves en el codigo ni en archivos versionados: `.env` sigue en `.gitignore` y `.env.example` solo tiene marcadores.

## Variables

`app/config.py` carga `.env` con `python-dotenv` al importarse. Las variables que lee el SDK son:

| Variable | Uso |
| --- | --- |
| `LANGSMITH_TRACING` | `true` activa el envio de trazas. |
| `LANGSMITH_API_KEY` | Clave personal de LangSmith. Nunca se imprime ni se escribe en el codigo. |
| `LANGSMITH_PROJECT` | Proyecto destino; en este caso `autonorte`. |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com`. |

`API_LANGSMITH` existe en el `.env` local, pero el SDK no la usa; la variable operativa es `LANGSMITH_API_KEY`. En `.env.example` ambas quedan como `pon_tu_clave_aqui`.

## Como reproducir

1. Copiar `.env.example` a `.env` y completar `LANGSMITH_API_KEY` con una clave real. No subir `.env`.
2. Activar el entorno: `source .venv/bin/activate`.
3. Reiniciar los datos: `python scripts/reiniciar_datos.py`.
4. Comprobar variables y hacer una ejecucion de prueba: `python scripts/verificar_langsmith.py`.
5. Generar trazas de agentes con el modelo encendido:
   - `python scripts/probar_agentes.py`, o
   - `uvicorn app.api.main:app --port 8000` y luego `python scripts/correr_casos.py`.
6. Abrir `https://smith.langchain.com`, entrar al proyecto `autonorte` y filtrar por el tag `autonorte`.

Si un script usa `langsmith.Client` directamente, debe importar `app.config` primero (o exportar las variables en la terminal); de lo contrario el cliente no encuentra la clave.

## Que se agrego al config de las invocaciones

En `app/agentes/orquestador.py` (`responder`), `app/agentes/citas.py` (`consultar`) y `app/agentes/cotizacion.py` (`consultar`) se agrego al `config`:

- `metadata={"hilo_id": hilo_id}` para buscar la conversacion por hilo.
- `tags=["autonorte", "orquestador" | "citas" | "cotizacion"]` para filtrar.
- `run_name="autonorte_orquestador" | "autonorte_citas" | "autonorte_cotizacion"` para identificar cada ejecucion.

No se cambio ninguna otra logica.

## Verificacion de anidamiento

Se ejecuto una conversacion real de cita con el modelo local y se consulto la traza `01a1a4e6-5ad9-7f50-9eff-c731c6a434b3` del proyecto `autonorte`. La jerarquia observada fue:

```text
autonorte_orquestador (chain, raiz)
  tools (chain)
    agente_citas (tool)
      autonorte_citas (chain)
        model / ChatOpenAI
        tools
          validar_solicitud (tool)
          consultar_disponibilidad (tool)
          preparar_cita (tool)
```

Los subagentes **si aparecen anidados** bajo la ejecucion del orquestador. No hizo falta propagar el `config` del padre a la llamada del subagente: LangChain/LangSmith propaga el contexto de traza por `contextvars` y el `ainvoke` que se hace dentro de la herramienta `agente_citas` queda como hijo del run de la herramienta. Si en otra version aparecieran sueltos, la correccion seria pasar el `RunnableConfig` del padre (o al menos `callbacks` y `metadata`) a la invocacion del subagente; en esta version no fue necesario.

## Capturas recomendadas

1. Lista de runs del proyecto `autonorte` filtrada por el tag `autonorte`, con `autonorte_orquestador` como raiz.
2. Arbol de la traza con `autonorte_orquestador` > `tools` > `agente_citas` > `autonorte_citas` > `validar_solicitud`, `consultar_disponibilidad` y `preparar_cita`.
3. Panel de metadata del run raiz mostrando `hilo_id`.
4. Una traza de cotizacion con `autonorte_cotizacion` anidada bajo `agente_cotizacion`.
5. Salida de `python scripts/verificar_langsmith.py` mostrando las variables definidas (sin la clave) y la ejecucion de prueba.

## Notas

- La traza de prueba se hizo con `HOY_FIJO=2026-10-16`, la fecha de los casos, para que la cita fuera valida.
- Las trazas de `scripts/demo_lcel.py` tambien llegan a LangSmith, pero no pasan por el orquestador; para ver la jerarquia de agentes hay que usar el chat o `scripts/probar_agentes.py`.
- LangSmith no reemplaza `var/trazas.jsonl`: ese archivo sigue siendo la evidencia local que leen `correr_casos.py` y las pruebas.
