"""Logica pura del proceso 2: funciones que reciben una conexion y devuelven diccionarios."""
import json
import unicodedata

from app import comun

MOTIVOS_DERIVACION = (
    "MONTO_REQUIERE_APROBACION", "SERVICIO_NO_ENCONTRADO", "FUERA_DE_ALCANCE",
    "LIMITE_DE_ITERACIONES", "ERROR_DE_SISTEMA",
)
DECISIONES = ("aceptar", "rechazar")


def normalizar(texto):
    """Minusculas sin tildes para comparar textos."""
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(caracter) != "Mn"
    )


def _texto_soles(monto):
    """Formatea un monto en soles: S/ 270.00."""
    return f"S/ {monto:,.2f}"


def _registrar(conn, clave, herramienta, resultado):
    with comun.transaccion(conn):
        comun.registrar_bitacora(conn, clave, herramienta, "OK" if resultado.get("ok") else resultado.get("codigo", "ERROR"))


def _siguiente_id(conn, tabla, columna, prefijo):
    fila = conn.execute(f"SELECT MAX({columna}) AS maxima FROM {tabla}").fetchone()
    if fila["maxima"] is None:
        return f"{prefijo}-0001"
    return f"{prefijo}-{int(fila['maxima'].split('-')[1]) + 1:04d}"


def _cotizacion(conn, id_cotizacion):
    fila = conn.execute(
        "SELECT * FROM cotizaciones WHERE id_cotizacion = ?", (id_cotizacion,)
    ).fetchone()
    if fila is None:
        return None
    return {
        "id_cotizacion": fila["id_cotizacion"],
        "vehiculo": fila["vehiculo"],
        "placa": fila["placa"],
        "lineas": json.loads(fila["lineas_json"]),
        "total": fila["total"],
        "estado": fila["estado"],
        "creada_en": fila["creada_en"],
    }


def _politica(conn, regla):
    fila = conn.execute("SELECT valor FROM politicas WHERE regla = ?", (regla,)).fetchone()
    if fila is None:
        return None
    return fila["valor"]


def consultar_tarifario(conn, descripcion):
    """Busca servicios del tarifario cuyas palabras clave aparezcan en la descripcion."""
    texto = normalizar(descripcion)
    encontradas = []
    for fila in conn.execute("SELECT codigo, servicio, precio_total_soles, palabras_clave FROM tarifario"):
        claves = [normalizar(palabra) for palabra in fila["palabras_clave"].split(";")]
        conteo = sum(1 for clave in claves if clave and clave in texto)
        if conteo:
            encontradas.append((conteo, {
                "codigo": fila["codigo"],
                "servicio": fila["servicio"],
                "precio_total_soles": fila["precio_total_soles"],
            }))
    encontradas.sort(key=lambda par: (-par[0], par[1]["codigo"]))
    coincidencias = [item for _, item in encontradas]

    if not coincidencias:
        resultado = comun.error(
            "SERVICIO_NO_ENCONTRADO",
            "No encontre ese servicio en el tarifario.",
            "Pedir al cliente que describa la falla de otra forma o derivar a una persona.",
        )
    elif len(coincidencias) == 1:
        resultado = {
            "ok": True,
            "coincidencias": coincidencias,
            "que_hacer": "Llama armar_cotizacion con ese codigo.",
        }
    else:
        resultado = {
            "ok": True,
            "coincidencias": coincidencias,
            "que_hacer": (
                "Si el cliente pidio varios servicios, usa todos los codigos. "
                "Si describio una sola falla, muestra las opciones y pregunta cual."
            ),
        }
    _registrar(conn, "", "consultar_tarifario", resultado)
    return resultado


def armar_cotizacion(conn, codigos, vehiculo, placa=""):
    """Crea la cotizacion con los precios del tarifario y calcula el total en codigo."""
    if isinstance(codigos, str):
        codigos = [codigos]
    codigos = [str(codigo).strip() for codigo in (codigos or []) if str(codigo).strip()]
    vehiculo = (vehiculo or "").strip()
    placa = (placa or "").strip().upper()

    if not codigos:
        resultado = comun.error(
            "SERVICIO_NO_ENCONTRADO",
            "No recibi ningun codigo del tarifario.",
            "Llama consultar_tarifario y usa un codigo de su lista.",
        )
        _registrar(conn, "", "armar_cotizacion", resultado)
        return resultado

    lineas = []
    faltantes = []
    for codigo in codigos:
        fila = conn.execute(
            "SELECT codigo, servicio, precio_total_soles FROM tarifario WHERE codigo = ?", (codigo,)
        ).fetchone()
        if fila is None:
            faltantes.append(codigo)
        else:
            lineas.append({
                "codigo": fila["codigo"],
                "servicio": fila["servicio"],
                "precio": fila["precio_total_soles"],
                "precio_texto": _texto_soles(fila["precio_total_soles"]),
            })

    if faltantes:
        resultado = comun.error(
            "SERVICIO_NO_ENCONTRADO",
            f"Codigos que no existen en el tarifario: {', '.join(faltantes)}.",
            "Llama consultar_tarifario de nuevo y usa solo codigos de su lista.",
        )
        _registrar(conn, "", "armar_cotizacion", resultado)
        return resultado

    total = round(sum(linea["precio"] for linea in lineas), 2)
    with comun.transaccion(conn):
        id_cotizacion = _siguiente_id(conn, "cotizaciones", "id_cotizacion", "COT")
        conn.execute(
            "INSERT INTO cotizaciones (id_cotizacion, vehiculo, placa, lineas_json, total, estado, creada_en)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id_cotizacion, vehiculo, placa, json.dumps(lineas, ensure_ascii=False), total, "validada", comun.ahora_texto()),
        )
        comun.registrar_bitacora(conn, id_cotizacion, "armar_cotizacion", "OK")
    return {
        "ok": True,
        "id_cotizacion": id_cotizacion,
        "vehiculo": vehiculo,
        "lineas": lineas,
        "total": total,
        "total_texto": _texto_soles(total),
        "que_hacer": (
            "Llama validar_politica_comercial con el id_cotizacion y usa los textos "
            "precio_texto y total_texto tal cual al informar al cliente."
        ),
    }


def validar_politica_comercial(conn, id_cotizacion, descuento_solicitado_pct=0):
    """Valida el monto y el descuento contra la politica comercial."""
    cotizacion = _cotizacion(conn, id_cotizacion)
    if cotizacion is None:
        resultado = comun.error(
            "COTIZACION_NO_ENCONTRADA",
            "No existe esa cotizacion.",
            "Llama armar_cotizacion para crearla.",
        )
        _registrar(conn, id_cotizacion, "validar_politica_comercial", resultado)
        return resultado

    try:
        descuento = float(descuento_solicitado_pct or 0)
    except (TypeError, ValueError):
        descuento = 0.0
    maximo = float(_politica(conn, "descuento_maximo_pct") or 0)
    monto_maximo = float(_politica(conn, "monto_maximo_sin_aprobacion_soles") or 0)
    vigencia = int(float(_politica(conn, "vigencia_cotizacion_dias") or 7))

    if cotizacion["total"] > monto_maximo:
        with comun.transaccion(conn):
            conn.execute(
                "UPDATE cotizaciones SET estado = 'pendiente_aprobacion' WHERE id_cotizacion = ?",
                (id_cotizacion,),
            )
            comun.registrar_bitacora(conn, id_cotizacion, "validar_politica_comercial", "MONTO_REQUIERE_APROBACION")
        return comun.error(
            "MONTO_REQUIERE_APROBACION",
            "El total necesita aprobacion del jefe de taller.",
            "Llama derivar_a_humano con motivo='MONTO_REQUIERE_APROBACION' y el id_cotizacion; "
            "explica el monto (total_texto) y que lo aprueba el jefe de taller.",
            id_cotizacion=id_cotizacion,
            total=cotizacion["total"],
            total_texto=_texto_soles(cotizacion["total"]),
        )

    with comun.transaccion(conn):
        conn.execute(
            "UPDATE testigos SET usado = 1 WHERE accion = 'cotizacion' AND clave = ? AND usado = 0",
            (id_cotizacion,),
        )
        testigo = comun.emitir_testigo(conn, "cotizacion", id_cotizacion)
        comun.registrar_bitacora(conn, id_cotizacion, "validar_politica_comercial", "OK")
    resultado = {
        "ok": True,
        "id_cotizacion": id_cotizacion,
        "total": cotizacion["total"],
        "total_texto": _texto_soles(cotizacion["total"]),
        "vigencia_dias": vigencia,
        "testigo": testigo,
        "que_hacer": (
            "Informa la cotizacion al cliente usando total_texto tal cual y pregunta si la acepta. "
            "Cuando la acepte, primero pregunta '¿Confirmas que programe el servicio?' y espera: "
            "solo con su confirmacion en el siguiente mensaje llama programar_servicio."
        ),
    }
    if descuento > maximo:
        resultado["aviso"] = {
            "codigo": "DESCUENTO_NO_PERMITIDO",
            "mensaje": "La politica no permite descuentos.",
            "que_hacer": "Informar la tarifa fija sin descuento.",
        }
    return resultado


def programar_servicio(conn, testigo, decision="aceptar"):
    """Consume el testigo y crea la orden de trabajo, o registra el rechazo."""
    decision = (decision or "").strip().lower()
    if decision not in DECISIONES:
        return comun.error(
            "DECISION_INVALIDA",
            "Solo se acepta 'aceptar' o 'rechazar'.",
            "Pregunta al cliente si acepta o rechaza; vuelve a llamar con 'aceptar' o 'rechazar'.",
        )

    with comun.transaccion(conn):
        fila_testigo = comun.consumir_testigo(conn, testigo, "cotizacion")
        if fila_testigo is None:
            comun.registrar_bitacora(conn, "", "programar_servicio", "TESTIGO_INVALIDO")
            return comun.error("TESTIGO_INVALIDO", "El testigo no es valido.", "Vuelve a llamar validar_politica_comercial")

        id_cotizacion = fila_testigo["clave"]
        cotizacion = _cotizacion(conn, id_cotizacion)
        if cotizacion is None:
            comun.registrar_bitacora(conn, id_cotizacion, "programar_servicio", "COTIZACION_NO_ENCONTRADA")
            return comun.error(
                "COTIZACION_NO_ENCONTRADA",
                "No existe esa cotizacion.",
                "Llama armar_cotizacion para crearla.",
            )

        if cotizacion["estado"] == "aceptada":
            fila_ot = conn.execute(
                "SELECT id_ot FROM ordenes_trabajo WHERE id_cotizacion = ? ORDER BY id_ot LIMIT 1",
                (id_cotizacion,),
            ).fetchone()
            comun.registrar_bitacora(conn, id_cotizacion, "programar_servicio", "OK")
            return {
                "ok": True,
                "id_cotizacion": id_cotizacion,
                "id_ot": fila_ot["id_ot"],
                "total": cotizacion["total"],
                "que_hacer": "Confirma al cliente la orden de trabajo e incluye el codigo de la orden (id_ot); avisa que el taller lo llamara para coordinar la fecha.",
            }

        if decision == "rechazar":
            conn.execute(
                "UPDATE cotizaciones SET estado = 'rechazada' WHERE id_cotizacion = ?", (id_cotizacion,)
            )
            comun.registrar_bitacora(conn, id_cotizacion, "programar_servicio", "OK")
            return {
                "ok": True,
                "id_cotizacion": id_cotizacion,
                "estado": "rechazada",
                "que_hacer": "Despidete del cliente y ofrecele otra ayuda.",
            }

        id_ot = _siguiente_id(conn, "ordenes_trabajo", "id_ot", "OT")
        conn.execute(
            "UPDATE cotizaciones SET estado = 'aceptada' WHERE id_cotizacion = ?", (id_cotizacion,)
        )
        conn.execute(
            "INSERT INTO ordenes_trabajo (id_ot, id_cotizacion, estado, creada_en) VALUES (?, ?, ?, ?)",
            (id_ot, id_cotizacion, "programada", comun.ahora_texto()),
        )
        comun.registrar_bitacora(conn, id_cotizacion, "programar_servicio", "OK")
        return {
            "ok": True,
            "id_cotizacion": id_cotizacion,
            "id_ot": id_ot,
            "total": cotizacion["total"],
            "que_hacer": "Confirma al cliente la orden de trabajo e incluye el codigo de la orden (id_ot); avisa que el taller lo llamara para coordinar la fecha.",
        }


QUE_HACER_DERIVACION = (
    "Explica al cliente el motivo y el total de la cotizacion (total_texto) si corresponde, y que "
    "un asesor lo contactara; termina tu respuesta sin llamar mas herramientas."
)


def _excepcion_de(conn, motivo, id_cotizacion):
    """Id de la excepcion ya encolada con el mismo motivo y la misma cotizacion, si existe."""
    for fila in conn.execute(
        "SELECT id, datos_json FROM cola_excepciones WHERE proceso = 'cotizacion' AND motivo = ? ORDER BY id",
        (motivo,),
    ):
        datos = json.loads(fila["datos_json"] or "{}")
        cotizacion = datos.get("cotizacion") or {}
        if datos.get("id_cotizacion") == id_cotizacion or cotizacion.get("id_cotizacion") == id_cotizacion:
            return fila["id"]
    return None


def derivar_a_humano(conn, motivo, consulta_original, id_cotizacion=""):
    """Encola la consulta para un asesor con la cotizacion y los pasos previos."""
    motivo = (motivo or "").strip().upper()
    if motivo not in MOTIVOS_DERIVACION:
        motivo = "OTRO"
    id_cotizacion = (id_cotizacion or "").strip()
    if id_cotizacion:
        existente = _excepcion_de(conn, motivo, id_cotizacion)
        if existente is not None:
            return {
                "ok": True,
                "id_excepcion": existente,
                "mensaje": "Un asesor revisará tu caso.",
                "que_hacer": QUE_HACER_DERIVACION,
            }
    datos_extra = {}
    if id_cotizacion:
        cotizacion = _cotizacion(conn, id_cotizacion)
        if cotizacion is not None:
            datos_extra["cotizacion"] = cotizacion
    with comun.transaccion(conn):
        resultado = comun.derivar(conn, "cotizacion", motivo, consulta_original, id_cotizacion, datos_extra=datos_extra)
        comun.registrar_bitacora(conn, id_cotizacion, "derivar_a_humano", "OK")
    resultado["que_hacer"] = QUE_HACER_DERIVACION
    return resultado
