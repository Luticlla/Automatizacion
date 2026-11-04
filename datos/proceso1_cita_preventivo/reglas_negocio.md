# Reglas del proceso 1: cita de mantenimiento preventivo

Fuente: Lab 02 (contrato, idempotencia, errores) y TO-BE del proyecto. Simplificado para el chat.

## Datos que el agente pide al cliente

solicitante, telefono, placa, tipo_servicio, fecha_solicitada. Nada mas. El campo `canal` lo pone el sistema en `web`.
Si el cliente describe un problema, se guarda en `descripcion`.

## Normalizacion y clave de idempotencia

1. placa en mayuscula y sin guion: `T4M-891` pasa a `T4M891`.
2. fecha en formato AAAA-MM-DD.
3. tipo_servicio en minuscula.
4. clave = SHA-256 de `placa|fecha|tipo`, primeros 32 caracteres hexadecimales.
5. Ejemplo verificado: `T4M891|2026-09-22|preventivo_10000` produce `1b114e68d6a3241784560e39cf0868d9`.
6. Si la clave ya existe en citas, no se crea otra: se devuelve la cita existente.

## Orden de verificaciones (se corta en la primera que falla)

1. Contrato de datos. Se devuelve la lista completa de errores, no solo el primero.
2. Clave ya existe: responder con la cita existente.
3. Descripcion con palabras de falla: derivar a una persona (posible correctivo). Palabras: ruido, falla, golpe, fuga, vibra, humo, no arranca, se calienta, frena mal, suena raro.
4. Kit: si el stock es 0, derivar a una persona para pedir el kit al proveedor. Esta regla va antes que la del cupo.
5. Cupo: tomar la primera hora libre de la fecha pedida. Si no hay, proponer las 3 proximas fechas posteriores con cupo (con su primera hora libre).
6. Duracion: si el servicio dura mas de 2 horas, derivar al jefe de taller para aprobacion. Duraciones en `kits_stock.csv`.
7. Todo bien: preparar la cita y pedir confirmacion al cliente.

## Registrar la cita (accion que no se puede deshacer)

Dos pasos. Primero se prepara y el servidor devuelve un testigo de un solo uso. Solo con ese testigo y el si del cliente se confirma.
Al confirmar: la hora pasa a `ocupado`, el stock del kit baja en 1 y se guarda la cita con id `CITA-0002`, `CITA-0003`...

## Mensajes de error (siempre con que_hacer)

| codigo | cuando | mensaje | que_hacer |
| --- | --- | --- | --- |
| CAMPO_FALTANTE | falta un campo obligatorio | Falta el campo X. | Pedir al cliente ese dato. |
| TELEFONO_INVALIDO | no son 9 digitos con 9 inicial | El telefono no es valido. | Pedir un telefono de 9 digitos que empiece en 9. |
| PLACA_INVALIDA | no cumple ABC-123 | La placa no tiene el formato correcto. | Pedir la placa con el formato T4M-891. |
| TIPO_INVALIDO | fuera del enumerado | Ese tipo de servicio no existe. | Ofrecer preventivo_5000, preventivo_10000 o preventivo_20000. |
| FECHA_INVALIDA | formato malo o anterior a hoy | La fecha no es valida. | Pedir una fecha desde hoy, formato AAAA-MM-DD. |
| FECHA_SIN_AGENDA | fuera de 2026-10-19 a 2026-10-30 | No hay agenda para esa fecha. | Pedir una fecha entre 2026-10-19 y 2026-10-30. |
| SIN_CUPO | no hay hora libre ese dia | No hay cupo en esa fecha. | Ofrecer las 3 fechas alternativas. |
| SIN_KIT | stock 0 | No hay kit disponible. | Derivar a una persona. |
| REQUIERE_APROBACION | duracion mayor a 2 horas | Este servicio necesita aprobacion del jefe de taller. | Derivar a una persona. |
| TESTIGO_INVALIDO | testigo usado, vencido o inexistente | El testigo no es valido. | Volver a preparar la cita. |

## Cola de excepciones (derivar a una persona)

Cada derivacion guarda: id, fecha_hora, proceso, motivo, consulta_original y datos (JSON con lo que se obtuvo hasta ese momento).
