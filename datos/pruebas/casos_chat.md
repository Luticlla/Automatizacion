# Casos de prueba en el chat

Hoy es 2026-10-16. Usar los casos en orden: P1-01 deja agendada la CITA-0002 y P2-01 a P2-03 forman una sola conversacion.
La columna Evidencia se llena al ejecutar: resultado obtenido, si paso y captura. Una prueba que falla y se corrige se repite.

| Caso | Escenario | Mensaje del cliente | Resultado esperado | Evidencia |
| --- | --- | --- | --- | --- |
| P1-01 | Cita sin problemas | Quiero cita de preventivo 10000 para mi placa A1B-234 el 2026-10-21. Soy Marco Ruiz Delgado, telefono 987654321. | Hay cupo (08:00, bahia B1). El agente pide confirmacion; con el si, queda registrada como CITA-0002. | |
| P1-02 | La cita ya existe (idempotencia) | Cita preventivo_10000, placa T4M-891, 2026-10-20, Marco Ruiz Delgado, 987654321. | Responde que la cita ya existe: CITA-0001, 2026-10-20 08:00, bahia B1. No crea otra. | |
| P1-03 | Sin cupo: 3 fechas alternativas | Preventivo_10000, placa B2C-345, fecha 2026-10-22, Ana Torres Rios, 912345678. | No hay cupo el 2026-10-22. Ofrece: 2026-10-23 08:00, 2026-10-26 08:00, 2026-10-27 08:00. | |
| P1-04 | Sin kit | Preventivo_5000, placa C3D-456, 2026-10-21, Luis Pardo Soto, 923456789. | No hay kit del servicio de 5000 km. Deriva a una persona (se guarda en la cola) y no agenda. | |
| P1-05 | Servicio de mas de 2 horas | Preventivo_20000, placa D4E-567, 2026-10-21, Rosa Diaz Luna, 934567890. | El servicio dura 3 horas: pide aprobacion del jefe de taller y deriva a una persona. No agenda. | |
| P1-06 | Datos invalidos | Placa ABC123, preventivo_15000, 2026-10-01, telefono 12345, me llamo Juan Perez. | Devuelve todos los errores a la vez: placa, tipo de servicio, fecha, telefono. No consulta la agenda. | |
| P1-07 | Falla en vez de preventivo | Quiero cita de preventivo_10000, placa E5F-678, 2026-10-23, mi auto suena raro al frenar. Elena Rojas Paz, 945678901. | Detecta una falla y deriva a una persona (posible correctivo). Opcional: ofrece pasar a cotizacion. | |
| P1-08 | Fuera de alcance | Cancela mi cita de manana. | Explica que no puede cancelar citas y deriva a una persona. No usa herramientas de agenda. | |
| P2-01 | Cotizacion simple | Mi Toyota Hilux frena mal y hace ruido al frenar. | Encuentra FRE-01 (Cambio de pastillas de freno delanteras) y cotiza S/ 270 (mano de obra 80 y repuestos 190). | |
| P2-02 | Pide descuento | Dame 10% de descuento en esa cotizacion. | Rechaza: la politica no permite descuentos. Mantiene S/ 270. | |
| P2-03 | Acepta la cotizacion | Esta bien, acepto la cotizacion de S/ 270. | Pide confirmacion, programa el servicio y genera OT-0001 a partir de COT-0001. | |
| P2-04 | Monto alto | Mi camioneta necesita cambio de embrague y cambio de correa de distribucion. | Cotiza EMB-01 (1600) y DIS-01 (900): total S/ 2500, mayor a S/ 2000. Deriva al jefe de taller. | |
| P2-05 | Servicio no encontrado | Quiero que le pongan aire acondicionado nuevo a mi auto. | No encuentra el servicio en el tarifario; pide otra descripcion o deriva a una persona. No inventa precio. | |
| P2-06 | Saludo y orquestador | Hola, buenas tardes. | El orquestador saluda y pregunta si quiere una cita de mantenimiento o una cotizacion de reparacion. | |

## Prueba de la herramienta sola (sin modelo)

- La clave de `T4M891|2026-09-22|preventivo_10000` debe ser `1b114e68d6a3241784560e39cf0868d9`.
- Confirmar con un testigo ya usado debe devolver TESTIGO_INVALIDO con que_hacer.
- Enviar dos veces la misma solicitud deja un solo registro.
