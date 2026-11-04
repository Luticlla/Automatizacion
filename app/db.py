"""Diseno de las dos bases SQLite: creacion, carga de semillas y conexiones."""
import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app import config

RUTA_PROCESO1 = config.RUTA_VAR / "proceso1.db"
RUTA_PROCESO2 = config.RUTA_VAR / "proceso2.db"

ESQUEMA_PROCESO1 = """
CREATE TABLE agenda (
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    bahia TEXT NOT NULL,
    tecnico TEXT NOT NULL,
    estado TEXT NOT NULL,
    PRIMARY KEY (fecha, hora, bahia)
);
CREATE TABLE kits (
    tipo_servicio TEXT PRIMARY KEY,
    kit_codigo TEXT NOT NULL,
    descripcion_kit TEXT NOT NULL,
    stock INTEGER NOT NULL,
    duracion_horas REAL NOT NULL
);
CREATE TABLE citas (
    id_cita TEXT PRIMARY KEY,
    clave TEXT UNIQUE,
    placa TEXT,
    fecha TEXT,
    hora TEXT,
    bahia TEXT,
    tecnico TEXT,
    tipo_servicio TEXT,
    solicitante TEXT,
    telefono TEXT,
    descripcion TEXT,
    canal TEXT,
    estado TEXT,
    creada_en TEXT
);
CREATE TABLE solicitudes_validadas (
    clave TEXT PRIMARY KEY,
    datos_json TEXT NOT NULL,
    creada_en TEXT NOT NULL
);
CREATE TABLE testigos (
    token TEXT PRIMARY KEY,
    accion TEXT NOT NULL,
    clave TEXT,
    usado INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL,
    expira_en TEXT NOT NULL
);
CREATE TABLE cola_excepciones (
    id TEXT PRIMARY KEY,
    fecha_hora TEXT NOT NULL,
    proceso TEXT NOT NULL,
    motivo TEXT NOT NULL,
    consulta_original TEXT NOT NULL,
    datos_json TEXT,
    estado TEXT NOT NULL
);
CREATE TABLE bitacora (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT,
    herramienta TEXT NOT NULL,
    codigo TEXT NOT NULL,
    ts TEXT NOT NULL
);
"""

CARGA_PROCESO1 = (
    ("agenda_cupos.csv", "agenda", ("fecha", "hora", "bahia", "tecnico", "estado")),
    ("kits_stock.csv", "kits", ("tipo_servicio", "kit_codigo", "descripcion_kit", "stock", "duracion_horas")),
    (
        "citas_semilla.csv",
        "citas",
        (
            "id_cita", "clave", "placa", "fecha", "hora", "bahia", "tecnico",
            "tipo_servicio", "solicitante", "telefono", "descripcion", "canal",
            "estado", "creada_en",
        ),
    ),
)

ESQUEMA_PROCESO2 = """
CREATE TABLE tarifario (
    codigo TEXT PRIMARY KEY,
    servicio TEXT NOT NULL,
    mano_obra_soles REAL NOT NULL,
    repuestos_soles REAL NOT NULL,
    precio_total_soles REAL NOT NULL,
    duracion_horas REAL NOT NULL,
    palabras_clave TEXT NOT NULL
);
CREATE TABLE politicas (
    regla TEXT PRIMARY KEY,
    valor REAL NOT NULL,
    fuente TEXT
);
CREATE TABLE cotizaciones (
    id_cotizacion TEXT PRIMARY KEY,
    vehiculo TEXT NOT NULL,
    placa TEXT,
    lineas_json TEXT NOT NULL,
    total REAL NOT NULL,
    estado TEXT NOT NULL,
    creada_en TEXT NOT NULL
);
CREATE TABLE ordenes_trabajo (
    id_ot TEXT PRIMARY KEY,
    id_cotizacion TEXT NOT NULL,
    estado TEXT NOT NULL,
    creada_en TEXT NOT NULL
);
CREATE TABLE testigos (
    token TEXT PRIMARY KEY,
    accion TEXT NOT NULL,
    clave TEXT,
    usado INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL,
    expira_en TEXT NOT NULL
);
CREATE TABLE cola_excepciones (
    id TEXT PRIMARY KEY,
    fecha_hora TEXT NOT NULL,
    proceso TEXT NOT NULL,
    motivo TEXT NOT NULL,
    consulta_original TEXT NOT NULL,
    datos_json TEXT,
    estado TEXT NOT NULL
);
CREATE TABLE bitacora (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT,
    herramienta TEXT NOT NULL,
    codigo TEXT NOT NULL,
    ts TEXT NOT NULL
);
"""

CARGA_PROCESO2 = (
    (
        "tarifario.csv",
        "tarifario",
        ("codigo", "servicio", "mano_obra_soles", "repuestos_soles", "precio_total_soles", "duracion_horas", "palabras_clave"),
    ),
    ("politicas_comerciales.csv", "politicas", ("regla", "valor", "fuente")),
)


def conectar(ruta):
    """Abre una conexion SQLite con la configuracion estandar del proyecto."""
    conn = sqlite3.connect(ruta, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def abrir_proceso1():
    """Conexion corta a var/proceso1.db que se cierra al terminar."""
    conn = conectar(RUTA_PROCESO1)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def abrir_proceso2():
    """Conexion corta a var/proceso2.db que se cierra al terminar."""
    conn = conectar(RUTA_PROCESO2)
    try:
        yield conn
    finally:
        conn.close()


def _borrar_archivos(ruta):
    for sufijo in ("", "-wal", "-shm"):
        archivo = Path(str(ruta) + sufijo)
        if archivo.exists():
            archivo.unlink()


def _valor(fila, columna):
    valor = fila.get(columna)
    if valor is None or valor == "":
        return None
    return valor


def _cargar_csv(conn, ruta, tabla, columnas):
    with open(ruta, newline="", encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))
    marcadores = ", ".join("?" for _ in columnas)
    sentencia = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcadores})"
    for fila in filas:
        conn.execute(sentencia, [_valor(fila, columna) for columna in columnas])
    return len(filas)


def reiniciar_proceso1():
    """Borra y recrea var/proceso1.db cargando los CSV de datos/proceso1_cita_preventivo/."""
    _borrar_archivos(RUTA_PROCESO1)
    conn = conectar(RUTA_PROCESO1)
    cargado = {}
    try:
        conn.executescript(ESQUEMA_PROCESO1)
        carpeta = config.RUTA_DATOS / "proceso1_cita_preventivo"
        for nombre_csv, tabla, columnas in CARGA_PROCESO1:
            cargado[tabla] = _cargar_csv(conn, carpeta / nombre_csv, tabla, columnas)
    finally:
        conn.close()
    return cargado


def reiniciar_proceso2():
    """Borra y recrea var/proceso2.db cargando los CSV de datos/proceso2_cotizacion_correctiva/."""
    _borrar_archivos(RUTA_PROCESO2)
    conn = conectar(RUTA_PROCESO2)
    cargado = {}
    try:
        conn.executescript(ESQUEMA_PROCESO2)
        carpeta = config.RUTA_DATOS / "proceso2_cotizacion_correctiva"
        for nombre_csv, tabla, columnas in CARGA_PROCESO2:
            cargado[tabla] = _cargar_csv(conn, carpeta / nombre_csv, tabla, columnas)
    finally:
        conn.close()
    return cargado


def iniciar_si_no_existen():
    """Crea las bases que falten a partir de las semillas de datos/."""
    if not RUTA_PROCESO1.exists():
        reiniciar_proceso1()
    if not RUTA_PROCESO2.exists():
        reiniciar_proceso2()
