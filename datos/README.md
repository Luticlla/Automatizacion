# Carpeta de datos (fase 2)

Datos **simulados** para los dos procesos de Autonorte Servicios Automotrices S.A.C. (Grupo 4). No contienen datos reales de la organizacion.
Estan pensados para un modelo pequeno (4B): codigos cortos, sin tildes en los CSV, un valor por celda y reglas que las herramientas aplican con codigo (el modelo no calcula ni decide precios ni cupos).

## Contenido

| Archivo | Para que sirve |
| --- | --- |
| proceso1_cita_preventivo/contrato_datos.json | Los 9 campos del Lab 02 y sus reglas |
| proceso1_cita_preventivo/agenda_cupos.csv | 10 dias habiles (2026-10-19 a 2026-10-30), 2 bahias, 3 horas por dia |
| proceso1_cita_preventivo/kits_stock.csv | Kit, stock y duracion por tipo de servicio |
| proceso1_cita_preventivo/citas_semilla.csv | Una cita ya registrada, para probar "la cita ya existe" |
| proceso1_cita_preventivo/reglas_negocio.md | Reglas, orden de verificaciones y mensajes de error |
| proceso2_cotizacion_correctiva/tarifario.csv | 12 servicios con precio fijo y palabras clave |
| proceso2_cotizacion_correctiva/politicas_comerciales.csv | 3 reglas del guardian comercial |
| proceso2_cotizacion_correctiva/reglas_negocio.md | Reglas, orden de pasos y mensajes de error |
| ui/textos_chat.json | Saludo, 3 sugerencias, pestañas del panel y textos del chat web |
| pruebas/casos_chat.md | 14 dialogos de prueba con resultado esperado y columna de evidencia |

## Convenciones

- CSV en UTF-8, separador coma. Dentro de `palabras_clave` el separador es punto y coma.
- Fecha `AAAA-MM-DD`, hora `HH:MM`, dinero en soles (S/) sin simbolo.
- "Hoy" para las pruebas es **2026-10-16**.
- Las tablas de SQLite que no tienen archivo (cotizaciones, ordenes de trabajo, cola de excepciones) se crean vacias; el panel lateral del chat web las lee.

## Supuestos que conviene validar

- Tarifas, duraciones y monto maximo sin aprobacion (S/ 2000): supuestos del equipo. El unico dato documentado es "tarifa fija (sin descuentos)" del AS-IS.
- Tecnicos, bahias y stock: inventados para las pruebas.

## No incluido a proposito (para mantenerlo simple)

Historial de vehiculos, ordenes de trabajo previas, reintentos con espera, temporizadores de 24 h y 48 h, webhook.
