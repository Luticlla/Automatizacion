"""Genera docs/inventario_agentes.md leyendo el codigo de los agentes."""
import ast
import importlib.util
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import config

RUTA_DOC = RAIZ / "docs" / "inventario_agentes.md"
RUTA_PROMPTS = RAIZ / "app" / "agentes" / "prompts.py"
RUTA_ORQUESTADOR = RAIZ / "app" / "agentes" / "orquestador.py"
RUTA_CITAS = RAIZ / "app" / "agentes" / "citas.py"
RUTA_COTIZACION = RAIZ / "app" / "agentes" / "cotizacion.py"
RUTA_SERVIDOR_CITAS = RAIZ / "app" / "mcp_citas" / "server.py"
RUTA_SERVIDOR_COTIZACION = RAIZ / "app" / "mcp_cotizaciones" / "server.py"


def leer_prompt(nombre):
    """Devuelve el texto de una constante de prompts.py usando AST."""
    arbol = ast.parse(RUTA_PROMPTS.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign):
            for destino in nodo.targets:
                if isinstance(destino, ast.Name) and destino.id == nombre:
                    return ast.literal_eval(nodo.value)
    return ""


def prohibiciones(texto):
    """Extrae las lineas con vineta que siguen a 'Prohibido:' en un prompt."""
    lineas = texto.splitlines()
    resultado = []
    dentro = False
    for linea in lineas:
        limpia = linea.strip()
        if limpia.startswith("Prohibido:"):
            dentro = True
            continue
        if dentro:
            if limpia.startswith("- "):
                resultado.append(limpia[2:].strip())
            elif not limpia:
                break
    return resultado


def es_decorador_tool(nodo):
    if isinstance(nodo, ast.Call):
        nodo = nodo.func
    return isinstance(nodo, ast.Attribute) and nodo.attr == "tool"


def herramientas_servidor(ruta):
    """Nombre, primera linea del docstring y linea de cada @mcp.tool()."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    herramientas = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.FunctionDef) and any(es_decorador_tool(d) for d in nodo.decorator_list):
            doc = ast.get_docstring(nodo) or ""
            primera = doc.strip().splitlines()[0].strip() if doc.strip() else "(sin docstring)"
            herramientas.append({
                "nombre": nodo.name,
                "primera": primera,
                "archivo": f"{ruta.relative_to(RAIZ)}:{nodo.lineno}",
            })
    return herramientas


def herramientas_orquestador():
    """Herramientas StructuredTool del orquestador, con su descripcion y return_direct."""
    arbol = ast.parse(RUTA_ORQUESTADOR.read_text(encoding="utf-8"))
    herramientas = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        if not (isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "from_function"):
            continue
        kwargs = {kw.arg: kw.value for kw in nodo.keywords if kw.arg}
        nombre = ast.literal_eval(kwargs["name"])
        descripcion = ast.literal_eval(kwargs["description"])
        return_direct = ast.literal_eval(kwargs.get("return_direct", ast.Constant(False)))
        primera = descripcion.strip().splitlines()[0].strip()
        herramientas.append({
            "nombre": nombre,
            "primera": primera,
            "return_direct": return_direct,
            "archivo": f"{RUTA_ORQUESTADOR.relative_to(RAIZ)}:{nodo.lineno}",
        })
    return herramientas


def limites_recursion(ruta):
    """Valores literales de recursion_limit que aparecen en el archivo."""
    texto = ruta.read_text(encoding="utf-8")
    return [valor.strip() for valor in re.findall(r'"recursion_limit":\s*([^,\n]+)', texto)]


def describir_limites(limites, es_orquestador=False):
    """Texto legible del recursion_limit para el documento."""
    if es_orquestador and limites and "if" in limites[0]:
        return "8 cuando decide el orquestador; 12 cuando atiende directo un flujo abierto"
    return ", ".join(limites)


def checkpointer():
    """Descripcion del checkpointer compartido."""
    texto = (RAIZ / "app" / "agentes" / "__init__.py").read_text(encoding="utf-8")
    if "InMemorySaver()" in texto:
        return "InMemorySaver compartido en `app/agentes/__init__.py` (`MEMORIA`); el estado vive en memoria del proceso."
    return "No se encontro InMemorySaver en app/agentes/__init__.py."


def modelo():
    """Modelo efectivo segun config.py y llm.py."""
    texto_llm = (RAIZ / "app" / "llm.py").read_text(encoding="utf-8")
    temperatura = re.search(r"temperature=(\d+)", texto_llm)
    return (
        f"ChatOpenAI local de `get_llm()`: `MODEL_BACKEND={config.MODEL_BACKEND}`, "
        f"`MODEL_NAME={config.MODEL_NAME}`, `base_url={config.MODEL_BASE_URL}`, "
        f"`temperature={temperatura.group(1) if temperatura else '?'}`."
    )


def tabla_herramientas(herramientas):
    lineas = ["| Herramienta | Primera linea del docstring / descripcion | Archivo y linea |", "| --- | --- | --- |"]
    for herramienta in herramientas:
        lineas.append(
            f"| `{herramienta['nombre']}` | {herramienta['primera']} | `{herramienta['archivo']}` |"
        )
    return "\n".join(lineas)


def seccion_agente(titulo, prompt, herramientas, limites, hilo, return_direct):
    lineas = [f"## {titulo}", ""]
    primera = prompt.strip().splitlines()[0].strip() if prompt.strip() else "(sin prompt)"
    lineas.append(f"**Rol:** {primera}")
    lineas.append("")
    lineas.append(f"**Modelo:** {modelo()}")
    lineas.append("")
    lineas.append("**Herramientas:**")
    lineas.append("")
    lineas.append(tabla_herramientas(herramientas))
    lineas.append("")
    lineas.append("**Prohibiciones del prompt:**")
    lineas.append("")
    for prohibicion in prohibiciones(prompt):
        lineas.append(f"- {prohibicion}")
    lineas.append("")
    lineas.append(f"**recursion_limit:** {limites}")
    lineas.append("")
    lineas.append(f"**Checkpointer:** {checkpointer()} Hilo: {hilo}.")
    lineas.append("")
    lineas.append(f"**return_direct:** {return_direct}")
    lineas.append("")
    return "\n".join(lineas)


def main():
    prompt_orquestador = leer_prompt("ORQUESTADOR")
    prompt_citas = leer_prompt("AGENTE_CITAS")
    prompt_cotizacion = leer_prompt("AGENTE_COTIZACION")

    herramientas_orq = herramientas_orquestador()
    herramientas_citas = herramientas_servidor(RUTA_SERVIDOR_CITAS)
    herramientas_cot = herramientas_servidor(RUTA_SERVIDOR_COTIZACION)

    limites_orq = limites_recursion(RUTA_ORQUESTADOR)
    limites_citas = limites_recursion(RUTA_CITAS)
    limites_cot = limites_recursion(RUTA_COTIZACION)

    deepagents = importlib.util.find_spec("deepagents")

    lineas = [
        "# Inventario de agentes",
        "",
        "Generado por `scripts/inventario_agentes.py` leyendo `app/agentes/` y los servidores MCP.",
        "",
        "## Aclaracion de arquitectura",
        "",
        "- El **orquestador es un agente supervisor** creado con `create_agent` de LangChain 1.x. Solo tiene dos herramientas (`agente_citas` y `agente_cotizacion`) con `return_direct=True`.",
        "- El **agente de citas** y el **agente de cotizacion** son **subagentes** creados tambien con `create_agent`; cada uno recibe solo las 5 herramientas de su servidor MCP.",
        "- **NO se usa el paquete `deepagents`**. La verificacion con `importlib.util.find_spec(\"deepagents\")` devuelve: "
        + ("instalado." if deepagents else "no instalado (None)."),
        "- La memoria es un `InMemorySaver` compartido por hilo; cada subagente usa `{hilo_id}:citas` o `{hilo_id}:cotizacion`.",
        "",
        "## Resumen",
        "",
        "| Agente | Rol | Modelo | Herramientas | recursion_limit | Checkpointer | return_direct |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        f"| Orquestador (supervisor) | {prompt_orquestador.strip().splitlines()[0]} | `{config.MODEL_NAME}` local | {len(herramientas_orq)} (`agente_citas`, `agente_cotizacion`) | {describir_limites(limites_orq, True)} | InMemorySaver | Si, en sus 2 herramientas |",
        f"| Agente de citas (subagente) | {prompt_citas.strip().splitlines()[0]} | `{config.MODEL_NAME}` local | {len(herramientas_citas)} MCP de citas | {describir_limites(limites_citas)} | InMemorySaver | No |",
        f"| Agente de cotizacion (subagente) | {prompt_cotizacion.strip().splitlines()[0]} | `{config.MODEL_NAME}` local | {len(herramientas_cot)} MCP de cotizaciones | {describir_limites(limites_cot)} | InMemorySaver | No |",
        "",
        seccion_agente(
            "Orquestador (supervisor)",
            prompt_orquestador,
            herramientas_orq,
            describir_limites(limites_orq, True),
            "`hilo_id` (o `{hilo_id}:{agente}` cuando atiende un flujo abierto)",
            "Si: `agente_citas` y `agente_cotizacion` tienen `return_direct=True`.",
        ),
        seccion_agente(
            "Agente de citas (subagente)",
            prompt_citas,
            herramientas_citas,
            describir_limites(limites_citas),
            "`{hilo_id}:citas`",
            "No: las herramientas MCP no declaran `return_direct`.",
        ),
        seccion_agente(
            "Agente de cotizacion (subagente)",
            prompt_cotizacion,
            herramientas_cot,
            describir_limites(limites_cot),
            "`{hilo_id}:cotizacion`",
            "No: las herramientas MCP no declaran `return_direct`.",
        ),
    ]

    RUTA_DOC.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Escrito {RUTA_DOC.relative_to(RAIZ)}")
    print(f"Herramientas: orquestador={len(herramientas_orq)}, citas={len(herramientas_citas)}, cotizacion={len(herramientas_cot)}")
    print(f"deepagents: {'instalado' if deepagents else 'no instalado'}")


if __name__ == "__main__":
    main()
