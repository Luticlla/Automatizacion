"""Grafo determinista del proceso 1: cita de mantenimiento preventivo (TO-BE)."""
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app import db
from app.mcp_citas import logica

CAMPOS_SOLICITUD = (
    "solicitante",
    "telefono",
    "placa",
    "tipo_servicio",
    "fecha_solicitada",
    "descripcion",
)


class EstadoProceso1(TypedDict, total=False):
    """Estado compartido por los nodos del proceso 1."""

    solicitud: dict
    consulta_original: str
    validacion: dict
    clave: str
    estado_validacion: str
    excepcion_id: str
    decision_humano: object
    resolucion: str
    aprobacion: str
    disponibilidad: dict
    consulta_cupo: dict
    consulta_kit: dict
    alternativas: list
    fecha_elegida: str
    resultado: dict
    cita: dict
    ruta_g1: str
    ruta_g2: str
    ruta_g3: str
    ruta_g3c: str
    ruta_g4: str
    ruta_g6: str
    ruta_g6b: str


def _datos_solicitud(estado):
    solicitud = estado.get("solicitud") or {}
    return {campo: solicitud.get(campo, "") for campo in CAMPOS_SOLICITUD}


def _consulta_original(estado):
    if estado.get("consulta_original"):
        return estado["consulta_original"]
    datos = _datos_solicitud(estado)
    return (
        f"Solicitud de cita {datos['tipo_servicio']} para {datos['placa']} "
        f"el {datos['fecha_solicitada']}. {datos['descripcion']}"
    ).strip()


def _texto_decision(respuesta, campo="decision"):
    if isinstance(respuesta, dict):
        valor = respuesta.get(campo)
        if valor is None:
            valor = respuesta.get("decision")
        if valor is None:
            valor = respuesta.get("resolucion")
    else:
        valor = respuesta
    return logica.sin_tildes(str(valor or "").strip().lower())


def _aprobado(respuesta):
    if isinstance(respuesta, dict) and "aprobado" in respuesta:
        valor = respuesta["aprobado"]
        if isinstance(valor, str):
            return _texto_decision({"aprobado": valor}, "aprobado") in (
                "aprobado", "aprobar", "si", "true", "1",
            )
        return bool(valor)
    return _texto_decision(respuesta) in ("aprobado", "aprobar", "si", "true", "1")


def _resultado_disponibilidad(estado):
    resultados = [estado.get("consulta_cupo"), estado.get("consulta_kit")]
    for codigo in ("SIN_KIT", "SIN_CUPO", "REQUIERE_APROBACION"):
        for resultado in resultados:
            if resultado and resultado.get("codigo") == codigo:
                return resultado
    for resultado in resultados:
        if resultado and resultado.get("ok"):
            return resultado
    return resultados[0] or {}


def s1v_validar(estado):
    """Valida el contrato, calcula la clave y clasifica la solicitud."""
    with db.abrir_proceso1() as conn:
        validacion = logica.validar_solicitud(conn, **_datos_solicitud(estado))
    return {"validacion": validacion, "clave": validacion.get("clave", "")}


def g1_contrato(estado):
    """Decide si la solicitud cumple el contrato de datos."""
    ruta = "s3n_normalizar" if estado.get("validacion", {}).get("ok") else "s2c_registrar_cola"
    return {"ruta_g1": ruta}


def s2c_registrar_cola(estado):
    """Registra la solicitud invalida en la cola de revision."""
    validacion = estado.get("validacion") or {}
    errores = validacion.get("errores") or []
    consulta = _consulta_original(estado)
    if errores:
        consulta = f"{consulta} | errores: {', '.join(error.get('codigo', '') for error in errores)}"
    with db.abrir_proceso1() as conn:
        derivacion = logica.derivar_a_humano(conn, "OTRO", consulta, estado.get("clave", ""))
    return {
        "excepcion_id": derivacion.get("id_excepcion", ""),
        "resultado": {
            "ok": False,
            "estado": "datos_invalidos",
            "errores": errores,
            "id_excepcion": derivacion.get("id_excepcion", ""),
        },
    }


def h1r_corregir(estado):
    """Pausa para que una persona corrija la solicitud en la cola."""
    respuesta = interrupt({
        "nodo": "H1r",
        "pregunta": "Corrige la solicitud en la cola de revision.",
        "clave": estado.get("clave", ""),
        "errores": (estado.get("validacion") or {}).get("errores") or [],
        "id_excepcion": estado.get("excepcion_id", ""),
    })
    return {
        "decision_humano": respuesta,
        "resultado": {
            "ok": False,
            "estado": "devuelta_para_correccion",
            "id_excepcion": estado.get("excepcion_id", ""),
            "errores": (estado.get("validacion") or {}).get("errores") or [],
        },
    }


def s3n_normalizar(estado):
    """Expone la clave de idempotencia ya calculada por validar_solicitud."""
    return {"clave": estado.get("validacion", {}).get("clave", "")}


def s2b_consultar_clave(estado):
    """Consulta el estado de la clave en el registro de citas."""
    return {"estado_validacion": estado.get("validacion", {}).get("estado", "")}


def g2_clave_existe(estado):
    """Decide si la clave ya tiene una cita registrada."""
    ruta = "s4d_devolver" if estado.get("estado_validacion") == "ya_existe" else "s5c_clasificar"
    return {"ruta_g2": ruta}


def s4d_devolver(estado):
    """Devuelve la cita ya registrada sin crear otra."""
    cita = estado.get("validacion", {}).get("cita")
    return {
        "cita": cita,
        "resultado": {"ok": True, "estado": "ya_existe", "cita": cita},
    }


def s5c_clasificar(estado):
    """Clasifica el servicio como preventivo o posible correctivo."""
    return {"estado_validacion": estado.get("validacion", {}).get("estado", "")}


def g3_preventivo(estado):
    """Decide si el caso sigue por preventivo o por revision humana."""
    ruta = "s_rev_encolar" if estado.get("estado_validacion") == "posible_falla" else "g3b_continuar"
    return {"ruta_g3": ruta}


def s_rev_encolar(estado):
    """Encola el caso para la revision del asesor."""
    with db.abrir_proceso1() as conn:
        derivacion = logica.derivar_a_humano(
            conn, "POSIBLE_CORRECTIVO", _consulta_original(estado), estado.get("clave", "")
        )
    return {"excepcion_id": derivacion.get("id_excepcion", "")}


def h2d_resolver(estado):
    """Pausa para que el asesor resuelva la clasificacion dudosa."""
    respuesta = interrupt({
        "nodo": "H2d",
        "pregunta": "Resuelve si el caso es correctivo o preventivo.",
        "clave": estado.get("clave", ""),
        "id_excepcion": estado.get("excepcion_id", ""),
    })
    decision = _texto_decision(respuesta)
    resolucion = "correctivo" if ("correct" in decision or "taller" in decision) else "preventivo"
    return {"decision_humano": respuesta, "resolucion": resolucion}


def g3c_resolucion(estado):
    """Decide la ruta segun lo que resolvio el asesor."""
    ruta = "s6d_notificar" if estado.get("resolucion") == "correctivo" else "g3b_continuar"
    return {"ruta_g3c": ruta}


def s6d_notificar(estado):
    """Notifica la derivacion a taller correctivo."""
    return {
        "resultado": {
            "ok": True,
            "estado": "derivado_correctivo",
            "id_excepcion": estado.get("excepcion_id", ""),
        }
    }


def g3b_continuar(estado):
    """Prepara el caso preventivo para las consultas en paralelo."""
    return {}


def and1(estado):
    """Abre las ramas paralelas de cupo y kit."""
    return {}


def s7c_consultar_cupo(estado):
    """Consulta la disponibilidad de bahia y tecnico."""
    with db.abrir_proceso1() as conn:
        resultado = logica.consultar_disponibilidad(conn, estado.get("clave", ""))
    return {"consulta_cupo": resultado}


def s8k_verificar_kit(estado):
    """Verifica la existencia del kit en el almacen."""
    with db.abrir_proceso1() as conn:
        resultado = logica.consultar_disponibilidad(conn, estado.get("clave", ""))
    return {"consulta_kit": resultado}


def and2(estado):
    """Une las ramas paralelas antes de evaluar cupo y kit."""
    return {}


def g4_clasificar(estado):
    """Decide si hay cupo y kit, falta kit o falta cupo."""
    resultado = _resultado_disponibilidad(estado)
    codigo = resultado.get("codigo", "")
    if resultado.get("ok"):
        ruta = "g4b_continuar"
    elif codigo == "SIN_KIT":
        ruta = "s_kit_encolar"
    elif codigo == "SIN_CUPO":
        ruta = "s9q_alternativas"
    elif codigo == "REQUIERE_APROBACION":
        ruta = "g4b_continuar"
    else:
        ruta = "no_implementado"
    return {"disponibilidad": resultado, "ruta_g4": ruta}


def s_kit_encolar(estado):
    """Encola el pedido del kit al proveedor."""
    with db.abrir_proceso1() as conn:
        derivacion = logica.derivar_a_humano(
            conn, "SIN_KIT", _consulta_original(estado), estado.get("clave", "")
        )
    return {"excepcion_id": derivacion.get("id_excepcion", "")}


def h3k_gestionar(estado):
    """Pausa para que una persona gestione el kit y acuerde la fecha."""
    respuesta = interrupt({
        "nodo": "H3k",
        "pregunta": "Gestiona el pedido del kit y acuerda la fecha con el cliente.",
        "clave": estado.get("clave", ""),
        "id_excepcion": estado.get("excepcion_id", ""),
    })
    return {
        "decision_humano": respuesta,
        "resultado": {
            "ok": True,
            "estado": "kit_gestionado",
            "id_excepcion": estado.get("excepcion_id", ""),
            "detalle": (
                "H3k se resolvio con una persona. El grafo no continua a G4b/G6 porque "
                "logica.py no actualiza el stock del kit."
            ),
        },
    }


def s9q_alternativas(estado):
    """Toma las tres fechas alternativas que devolvio la consulta."""
    resultado = estado.get("disponibilidad") or _resultado_disponibilidad(estado)
    return {"alternativas": resultado.get("alternativas") or []}


def s9a_proponer(estado):
    """Propone las tres fechas alternativas al cliente."""
    alternativas = estado.get("alternativas") or []
    texto = ", ".join(f"{alternativa['fecha']} {alternativa['hora']}" for alternativa in alternativas)
    return {"resultado": {"ok": True, "estado": "alternativas_propuestas", "alternativas": alternativas, "texto": texto}}


def g5_eleccion(estado):
    """Continua a la espera del cliente; el plazo de 24 h no esta implementado."""
    return {}


def ic_msg(estado):
    """Pausa para que el cliente elija una de las fechas propuestas."""
    respuesta = interrupt({
        "nodo": "IC_msg",
        "pregunta": "Elige una de las fechas alternativas.",
        "alternativas": estado.get("alternativas") or [],
    })
    if isinstance(respuesta, dict):
        fecha = respuesta.get("fecha") or respuesta.get("fecha_solicitada") or ""
    else:
        fecha = str(respuesta or "")
    solicitud = dict(estado.get("solicitud") or {})
    if fecha:
        solicitud["fecha_solicitada"] = fecha
    return {"solicitud": solicitud, "fecha_elegida": fecha}


def ic_t24(estado):
    """Marca el vencimiento de 24 horas; el temporizador no esta implementado."""
    return {"resultado": {"ok": False, "estado": "plazo_vencido", "detalle": "Temporizador de 24 h no implementado."}}


def s10d_desistida(estado):
    """Registra la solicitud como desistida."""
    return {"resultado": {"ok": False, "estado": "desistida"}}


def g4b_continuar(estado):
    """Continua hacia la validacion de duracion."""
    return {}


def g6_duracion(estado):
    """Decide si la duracion supera las dos horas."""
    resultado = estado.get("disponibilidad") or _resultado_disponibilidad(estado)
    requiere = resultado.get("codigo") == "REQUIERE_APROBACION" or (
        resultado.get("ok") and float(resultado.get("duracion_horas") or 0) > 2
    )
    if requiere:
        return {"ruta_g6": "s_apr_encolar"}
    if not resultado.get("ok"):
        return {"ruta_g6": "no_implementado"}
    return {"ruta_g6": "g6b_decision", "aprobacion": "automatico"}


def s_apr_encolar(estado):
    """Encola la aprobacion del jefe de taller."""
    with db.abrir_proceso1() as conn:
        derivacion = logica.derivar_a_humano(
            conn, "REQUIERE_APROBACION", _consulta_original(estado), estado.get("clave", "")
        )
    return {"excepcion_id": derivacion.get("id_excepcion", "")}


def h4a_aprobar(estado):
    """Pausa para que el jefe de taller apruebe la asignacion excepcional."""
    respuesta = interrupt({
        "nodo": "H4a",
        "pregunta": "Aprueba la asignacion excepcional de mas de 2 horas.",
        "clave": estado.get("clave", ""),
        "id_excepcion": estado.get("excepcion_id", ""),
        "disponibilidad": estado.get("disponibilidad") or {},
    })
    aprobacion = "aprobado" if _aprobado(respuesta) else "rechazado"
    return {"decision_humano": respuesta, "aprobacion": aprobacion}


def g6b_decision(estado):
    """Decide si registra la cita o cierra el caso rechazado."""
    if estado.get("aprobacion") == "rechazado":
        return {
            "ruta_g6b": "end_4",
            "resultado": {"ok": False, "estado": "rechazada_por_jefe"},
        }
    return {"ruta_g6b": "s12r_registrar"}


def s12r_registrar(estado):
    """Registra la cita con la clave unica y el testigo de un solo uso."""
    with db.abrir_proceso1() as conn:
        preparacion = logica.preparar_cita(conn, estado.get("clave", ""))
        if not preparacion.get("ok"):
            return {"resultado": preparacion}
        confirmacion = logica.confirmar_cita(conn, preparacion["testigo"])
    return {"resultado": confirmacion, "cita": confirmacion if confirmacion.get("ok") else None}


def s14c_confirmar(estado):
    """Prepara la confirmacion inmediata al cliente."""
    resultado = dict(estado.get("resultado") or {})
    resultado["estado"] = "confirmada"
    resultado["mensaje"] = (
        f"Cita {resultado.get('id_cita', '')} confirmada para "
        f"{resultado.get('fecha', '')} a las {resultado.get('hora', '')}."
    )
    return {"resultado": resultado}


def s_cls(estado):
    """Clasifica un error de sistema; la ruta de error no esta implementada."""
    return {"resultado": {"ok": False, "codigo": "ERROR_DE_SISTEMA", "clase": "sistema"}}


def s13f_cola_fallidos(estado):
    """Encola un caso fallido; la ruta de error no esta implementada."""
    with db.abrir_proceso1() as conn:
        derivacion = logica.derivar_a_humano(
            conn, "ERROR_DE_SISTEMA", _consulta_original(estado), estado.get("clave", "")
        )
    return {"excepcion_id": derivacion.get("id_excepcion", "")}


def h5r_reprogramar(estado):
    """Reprograma la cita por falta de kit; el plazo del proveedor no esta implementado."""
    return {"resultado": {"ok": True, "estado": "reprogramada_por_kit"}}


def no_implementado(estado):
    """Cierra una ruta que el BPMN define pero el proyecto no implementa."""
    return {
        "resultado": {
            "ok": False,
            "estado": "no_implementado",
            "detalle": "Ruta sin implementacion en el proyecto.",
        }
    }


def _terminal(estado):
    return {}


def construir_grafo():
    """Compila el grafo del proceso 1 con memoria en proceso para los HITL."""
    constructor = StateGraph(EstadoProceso1)

    nodos = {
        "s1v_validar": s1v_validar,
        "g1_contrato": g1_contrato,
        "s2c_registrar_cola": s2c_registrar_cola,
        "h1r_corregir": h1r_corregir,
        "s3n_normalizar": s3n_normalizar,
        "s2b_consultar_clave": s2b_consultar_clave,
        "g2_clave_existe": g2_clave_existe,
        "s4d_devolver": s4d_devolver,
        "s5c_clasificar": s5c_clasificar,
        "g3_preventivo": g3_preventivo,
        "s_rev_encolar": s_rev_encolar,
        "h2d_resolver": h2d_resolver,
        "g3c_resolucion": g3c_resolucion,
        "s6d_notificar": s6d_notificar,
        "g3b_continuar": g3b_continuar,
        "and1": and1,
        "s7c_consultar_cupo": s7c_consultar_cupo,
        "s8k_verificar_kit": s8k_verificar_kit,
        "and2": and2,
        "g4_clasificar": g4_clasificar,
        "s_kit_encolar": s_kit_encolar,
        "h3k_gestionar": h3k_gestionar,
        "s9q_alternativas": s9q_alternativas,
        "s9a_proponer": s9a_proponer,
        "g5_eleccion": g5_eleccion,
        "ic_msg": ic_msg,
        "ic_t24": ic_t24,
        "s10d_desistida": s10d_desistida,
        "g4b_continuar": g4b_continuar,
        "g6_duracion": g6_duracion,
        "s_apr_encolar": s_apr_encolar,
        "h4a_aprobar": h4a_aprobar,
        "g6b_decision": g6b_decision,
        "s12r_registrar": s12r_registrar,
        "s14c_confirmar": s14c_confirmar,
        "s_cls": s_cls,
        "s13f_cola_fallidos": s13f_cola_fallidos,
        "h5r_reprogramar": h5r_reprogramar,
        "no_implementado": no_implementado,
        "be_cupo": _terminal,
        "be_kit": _terminal,
        "be_alt": _terminal,
        "be_err": _terminal,
        "bt_kit": _terminal,
        "end_1": _terminal,
        "end_2": _terminal,
        "end_3": _terminal,
        "end_4": _terminal,
        "end_5": _terminal,
        "end_6": _terminal,
        "end_7": _terminal,
    }
    for nombre, funcion in nodos.items():
        constructor.add_node(nombre, funcion)

    constructor.add_edge(START, "s1v_validar")
    constructor.add_edge("s1v_validar", "g1_contrato")
    constructor.add_conditional_edges(
        "g1_contrato",
        lambda estado: estado["ruta_g1"],
        {"s3n_normalizar": "s3n_normalizar", "s2c_registrar_cola": "s2c_registrar_cola"},
    )
    constructor.add_edge("s2c_registrar_cola", "h1r_corregir")
    constructor.add_edge("h1r_corregir", "end_1")
    constructor.add_edge("s3n_normalizar", "s2b_consultar_clave")
    constructor.add_edge("s2b_consultar_clave", "g2_clave_existe")
    constructor.add_conditional_edges(
        "g2_clave_existe",
        lambda estado: estado["ruta_g2"],
        {"s4d_devolver": "s4d_devolver", "s5c_clasificar": "s5c_clasificar"},
    )
    constructor.add_edge("s4d_devolver", "end_2")
    constructor.add_edge("s5c_clasificar", "g3_preventivo")
    constructor.add_conditional_edges(
        "g3_preventivo",
        lambda estado: estado["ruta_g3"],
        {"s_rev_encolar": "s_rev_encolar", "g3b_continuar": "g3b_continuar"},
    )
    constructor.add_edge("s_rev_encolar", "h2d_resolver")
    constructor.add_edge("h2d_resolver", "g3c_resolucion")
    constructor.add_conditional_edges(
        "g3c_resolucion",
        lambda estado: estado["ruta_g3c"],
        {"s6d_notificar": "s6d_notificar", "g3b_continuar": "g3b_continuar"},
    )
    constructor.add_edge("s6d_notificar", "end_3")
    constructor.add_edge("g3b_continuar", "and1")
    constructor.add_edge("and1", "s7c_consultar_cupo")
    constructor.add_edge("and1", "s8k_verificar_kit")
    constructor.add_edge("s7c_consultar_cupo", "and2")
    constructor.add_edge("s8k_verificar_kit", "and2")
    constructor.add_edge("and2", "g4_clasificar")
    constructor.add_conditional_edges(
        "g4_clasificar",
        lambda estado: estado["ruta_g4"],
        {
            "g4b_continuar": "g4b_continuar",
            "s_kit_encolar": "s_kit_encolar",
            "s9q_alternativas": "s9q_alternativas",
            "no_implementado": "no_implementado",
        },
    )
    constructor.add_edge("s_kit_encolar", "h3k_gestionar")
    constructor.add_edge("h3k_gestionar", "end_7")
    constructor.add_edge("s9q_alternativas", "s9a_proponer")
    constructor.add_edge("s9a_proponer", "g5_eleccion")
    constructor.add_edge("g5_eleccion", "ic_msg")
    constructor.add_edge("ic_msg", "s1v_validar")
    constructor.add_edge("ic_t24", "s10d_desistida")
    constructor.add_edge("s10d_desistida", "end_4")
    constructor.add_edge("g4b_continuar", "g6_duracion")
    constructor.add_conditional_edges(
        "g6_duracion",
        lambda estado: estado["ruta_g6"],
        {
            "s_apr_encolar": "s_apr_encolar",
            "g6b_decision": "g6b_decision",
            "no_implementado": "no_implementado",
        },
    )
    constructor.add_edge("s_apr_encolar", "h4a_aprobar")
    constructor.add_edge("h4a_aprobar", "g6b_decision")
    constructor.add_conditional_edges(
        "g6b_decision",
        lambda estado: estado["ruta_g6b"],
        {"s12r_registrar": "s12r_registrar", "end_4": "end_4"},
    )
    constructor.add_conditional_edges(
        "s12r_registrar",
        lambda estado: "s14c_confirmar" if (estado.get("resultado") or {}).get("ok") else "end_5",
        {"s14c_confirmar": "s14c_confirmar", "end_5": "end_5"},
    )
    constructor.add_edge("s14c_confirmar", "end_6")
    constructor.add_edge("s_cls", "s13f_cola_fallidos")
    constructor.add_edge("s13f_cola_fallidos", "end_5")
    constructor.add_edge("bt_kit", "h5r_reprogramar")
    constructor.add_edge("h5r_reprogramar", "end_7")
    constructor.add_edge("no_implementado", END)
    for fin in ("end_1", "end_2", "end_3", "end_4", "end_5", "end_6", "end_7"):
        constructor.add_edge(fin, END)

    return constructor.compile(checkpointer=InMemorySaver())
