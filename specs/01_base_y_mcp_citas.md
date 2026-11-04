# Especificación 01 — Base compartida y servidor MCP de citas

Lee antes: `AGENTS.md`, `datos/README.md`, `datos/proceso1_cita_preventivo/reglas_negocio.md` y `contrato_datos.json`. Esas reglas son la fuente; esta especificación dice cómo implementarlas.

## Parte A. Base compartida

### `app/config.py`
Lee `.env` (python-dotenv). Expone: `MODEL_BACKEND`, `MODEL_BASE_URL`, `MODEL_NAME`, `hoy()` (devuelve `HOY_FIJO` como `date` si existe; si no, la fecha del sistema), `RUTA_DATOS` (`datos/`) y `RUTA_VAR` (`var/`, se crea si no existe).

### `app/db.py`
- Dos bases SQLite: `var/proceso1.db` y `var/proceso2.db`. Conexión con `timeout=5`, `PRAGMA journal_mode=WAL`, `row_factory=sqlite3.Row`.
- `reiniciar_proceso1()` borra y recrea `proceso1.db` cargando los CSV de `datos/proceso1_cita_preventivo/`. Un `reiniciar_proceso2()` análogo lo implementa la especificación 02 en el mismo archivo.
- `iniciar_si_no_existen()` llama a los dos reinicios solo si el archivo de base no existe.
- Tablas del proceso 1:
  - `agenda(fecha, hora, bahia, tecnico, estado)`, clave primaria `(fecha, hora, bahia)`.
  - `kits(tipo_servicio PK, kit_codigo, descripcion_kit, stock, duracion_horas)`.
  - `citas(id_cita PK, clave UNIQUE, placa, fecha, hora, bahia, tecnico, tipo_servicio, solicitante, telefono, descripcion, canal, estado, creada_en)`. Las columnas que no vienen en `citas_semilla.csv` quedan nulas.
  - `solicitudes_validadas(clave PK, datos_json, creada_en)`.
  - `testigos(token PK, accion, clave, usado, creado_en, expira_en)`.
  - `cola_excepciones(id PK, fecha_hora, proceso, motivo, consulta_original, datos_json, estado)`.
  - `bitacora(id PK, clave, herramienta, codigo, ts)`.
- Ids secuenciales: `CITA-0002` es la primera cita nueva (la semilla trae `CITA-0001`); siguiente = máximo existente + 1, con 4 dígitos.
- `scripts/reiniciar_datos.py` llama a `reiniciar_proceso1()` y `reiniciar_proceso2()` (si ya existe) e imprime qué cargó.

### `app/comun.py`
- `error(codigo, mensaje, que_hacer, clase="datos", **extra)` devuelve el diccionario estándar de `AGENTS.md`.
- `emitir_testigo(conn, accion, clave)` crea `secrets.token_hex(4).upper()` con prefijo `T-` (por ejemplo `T-9F3A21BC`), lo guarda con vigencia de 30 minutos y lo devuelve.
- `consumir_testigo(conn, token, accion)` valida que exista, sea de esa acción, no esté usado ni vencido; lo marca usado dentro de la misma transacción; devuelve la fila o `None`.
- `registrar_bitacora(conn, clave, herramienta, codigo)`.
- `derivar(conn, proceso, motivo, consulta_original, clave="")` inserta en `cola_excepciones` (`EXC-0001`, `EXC-0002`...) con `datos_json` que incluye la solicitud validada de esa clave (si existe) y la lista de pasos de `bitacora` de esa clave. Estado `pendiente`. Devuelve `{"ok": true, "id_excepcion": ..., "mensaje": "Un asesor revisará tu caso."}`.
- Reintento simple: si SQLite devuelve `database is locked`, reintentar hasta 3 veces con 0.2 s; si sigue, error con `clase: "transitorio"`.
- Todo bloque que escriba usa transacción (`BEGIN IMMEDIATE`).

## Parte B. Servidor MCP de citas

Archivos: `app/mcp_citas/logica.py` (funciones puras que reciben la conexión y devuelven diccionarios) y `app/mcp_citas/server.py` (FastMCP del paquete `mcp`, transporte stdio, una función decorada por herramienta que solo llama a `logica`). Se arranca con `python -m app.mcp_citas.server`.

Regla de oro: **ninguna herramienta lanza excepciones ni imprime en stdout**. Cada llamada envuelve la lógica con captura de excepciones → `error(..., clase="sistema")`, y registra el detalle en stderr.

### Normalización
- `placa`: mayúsculas y sin espacios al borde. Se valida con guion (`^[A-Z][A-Z0-9]{2}-[0-9]{3}$`). Para la clave se quita el guion.
- `tipo_servicio`: minúsculas.
- `fecha_solicitada`: `AAAA-MM-DD`, fecha real, no anterior a `hoy()`.
- `telefono`: sin espacios; patrón `^9[0-9]{8}$`.
- `canal`: siempre `web` (no es parámetro).
- `clave`: SHA-256 de `placa_sin_guion|fecha|tipo`, primeros 32 caracteres hexadecimales.

### Las 5 herramientas

**1. `validar_solicitud(solicitante="", telefono="", placa="", tipo_servicio="", fecha_solicitada="", descripcion="")`**
Hace los pasos 1 a 3 del orden de verificaciones, en este orden y cortando en el primero que aplique:
1. Contrato: devuelve **todos** los errores juntos: `{"ok": false, "clase": "datos", "errores": [{codigo, mensaje, que_hacer}, ...]}` usando los códigos de la tabla de `reglas_negocio.md` (`CAMPO_FALTANTE`, `TELEFONO_INVALIDO`, `PLACA_INVALIDA`, `TIPO_INVALIDO`, `FECHA_INVALIDA`). Con campos faltantes, un error `CAMPO_FALTANTE` por campo.
2. Si el contrato pasa: calcula la clave y guarda la solicitud normalizada en `solicitudes_validadas`.
3. Clave ya existe en `citas`: `{"ok": true, "estado": "ya_existe", "cita": {id_cita, fecha, hora, bahia, tecnico}, "que_hacer": "Informa al cliente que su cita ya existe con esos datos y no crees otra."}`.
4. `descripcion` con alguna palabra de falla (lista en `reglas_negocio.md`, comparar sin tildes y en minúsculas): `{"ok": true, "estado": "posible_falla", "clave": ..., "que_hacer": "Llama derivar_a_humano con motivo='POSIBLE_CORRECTIVO' y la clave. Explica que parece una reparación y ofrece cotizarla."}`.
5. Todo bien: `{"ok": true, "estado": "valida", "clave": ..., "que_hacer": "Llama consultar_disponibilidad con la clave."}`.
Docstring: dice que se usa cuando ya están los 5 datos y que NO se usa para cancelar ni reprogramar citas.

**2. `consultar_disponibilidad(clave)`**
Lee la solicitud guardada por la clave (si no existe: `error("CLAVE_DESCONOCIDA", ..., "Llama validar_solicitud primero.")`). Aplica los pasos 4 a 6, en este orden:
1. Fecha dentro de la agenda (`2026-10-19` a `2026-10-30`); si no: `FECHA_SIN_AGENDA`.
2. Kit: stock 0 → `SIN_KIT`, con `que_hacer`: "Llama derivar_a_humano con motivo='SIN_KIT' y la clave; avisa al cliente."
3. Cupo: primera hora libre de la fecha (orden por hora, luego bahía). Si no hay: `SIN_CUPO` con `alternativas`: las 3 próximas fechas posteriores con cupo, cada una con su primera hora libre (`[{"fecha":..., "hora":...}, ...]`) y `que_hacer`: "Ofrece esas 3 fechas. Si el cliente elige una, llama validar_solicitud otra vez con la misma información y la fecha nueva."
4. Duración del servicio mayor a 2 horas (tabla `kits`): `REQUIERE_APROBACION`, `que_hacer`: "Llama derivar_a_humano con motivo='REQUIERE_APROBACION' y la clave; explica que lo aprueba el jefe de taller."
5. Todo bien: `{"ok": true, "hora", "bahia", "tecnico", "kit", "duracion_horas", "que_hacer": "Llama preparar_cita con la clave."}`. No reserva nada.

**3. `preparar_cita(clave)`**
Repite las verificaciones de `consultar_disponibilidad` (esta herramienta es la autoridad, no confía en llamadas previas). Si pasan: emite un testigo con acción `cita` y devuelve `{"ok": true, "resumen": {placa, tipo_servicio, fecha, hora, bahia, tecnico}, "testigo": "T-XXXXXXXX", "que_hacer": "Muestra el resumen al cliente y pide que confirme. NO llames confirmar_cita hasta que el cliente responda en un mensaje nuevo."}`. Si no pasan: el mismo error que daría `consultar_disponibilidad`. No modifica agenda ni stock.

**4. `confirmar_cita(testigo)`**
En una sola transacción: consume el testigo (si falla: `TESTIGO_INVALIDO`, que_hacer "Vuelve a llamar preparar_cita"); si la clave ya está en `citas` devuelve esa cita con `estado: "ya_existe"` (idempotente, no duplica); verifica que el hueco siga libre (si no: `SIN_CUPO`); marca la hora como `ocupado`; baja en 1 el stock del kit; inserta la cita con el siguiente id y estado `confirmada`; registra bitácora. Devuelve `{"ok": true, "id_cita", "fecha", "hora", "bahia", "tecnico", "que_hacer": "Confirma al cliente la cita con esos datos."}`.

**5. `derivar_a_humano(motivo, consulta_original, clave="")`**
Motivos válidos: `POSIBLE_CORRECTIVO`, `SIN_KIT`, `REQUIERE_APROBACION`, `FUERA_DE_ALCANCE`, `LIMITE_DE_ITERACIONES`, `ERROR_DE_SISTEMA`. Un motivo desconocido se acepta pero se guarda como `OTRO`. Usa `comun.derivar` con `proceso = "citas"`. Docstring: se usa cuando una regla lo indica o el cliente pide algo fuera de alcance (cancelar, reprogramar, otra consulta).

Cada herramienta registra una línea en `bitacora` con su nombre y el código de resultado (`OK` o el código de error).

## Scripts y pruebas

- `scripts/probar_mcp_citas.py`: arranca el servidor por stdio con el cliente del paquete `mcp`, lista las 5 herramientas (nombre y docstring) y ejecuta el recorrido feliz y tres errores. Imprime cada llamada y respuesta. Sin modelo.
- `tests/test_citas.py` (pytest, sobre `logica.py` con una base temporal reiniciada):
  - La clave de `T4M891|2026-09-22|preventivo_10000` es `1b114e68d6a3241784560e39cf0868d9`.
  - Toda respuesta con `ok: false` trae `codigo`, `mensaje`, `que_hacer` y `clase` (o la lista `errores` con esos campos).
  - Contrato: placa `ABC123`, tipo `preventivo_15000`, fecha `2026-10-01` y teléfono `12345` devuelven los cuatro errores a la vez.
  - Orden: tipo `preventivo_5000` (stock 0) en una fecha sin cupo devuelve `SIN_KIT`, no `SIN_CUPO`.
  - Alternativas: para `2026-10-22` devuelve `2026-10-23 08:00`, `2026-10-26 08:00`, `2026-10-27 08:00`.
  - Duración: `preventivo_20000` en una fecha con cupo devuelve `REQUIERE_APROBACION`.
  - Idempotencia: enviar dos veces la solicitud de `T4M-891`, `2026-10-20`, `preventivo_10000` devuelve `ya_existe` con `CITA-0001`; confirmar dos veces el mismo testigo deja una sola cita.
  - Testigo reusado: segunda confirmación con el mismo testigo devuelve `TESTIGO_INVALIDO`.
  - Recorrido feliz: validar → disponibilidad → preparar → confirmar crea `CITA-0002`, la hora queda `ocupado` y el stock baja en 1.
  - Falla: descripción "suena raro al frenar" devuelve `posible_falla`.
  - `derivar_a_humano` agrega una fila en la cola con consulta original y pasos.

## Criterios de aceptación

1. `pytest tests/test_citas.py` pasa completo.
2. `python scripts/probar_mcp_citas.py` lista exactamente 5 herramientas y el recorrido feliz termina en `CITA-0002`.
3. `grep -rn "print(" app/mcp_citas app/comun.py app/db.py` no devuelve nada (o solo salidas a `sys.stderr`).
4. `datos/` quedó sin cambios.
