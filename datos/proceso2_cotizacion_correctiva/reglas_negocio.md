# Reglas del proceso 2: cotizacion de reparacion correctiva

Fuente: AS-IS y TO-BE de cotizacion. El agente guardian del TO-BE pasa a ser la herramienta `validar_politica_comercial` (codigo, no modelo).

## Datos que el agente pide al cliente

marca y modelo del vehiculo, y la falla o el servicio que necesita. La placa es opcional.

## Orden de pasos

1. Buscar en el tarifario por palabras clave de la falla o del servicio (el codigo normaliza tildes y mayusculas). Si hay varias coincidencias, mostrarlas y pedir al cliente que elija.
2. Armar la cotizacion: lineas con codigo, servicio y precio, y total. El precio sale siempre del tarifario; el modelo nunca lo escribe por su cuenta.
3. Validar contra la politica comercial (`politicas_comerciales.csv`):
   - Descuento: el maximo es 0 %. Si el cliente pide descuento, se rechaza y se informa la tarifa fija.
   - Monto: si el total supera S/ 2000, derivar al jefe de taller para aprobacion.
4. Si pasa la validacion, el servidor emite un testigo de un solo uso y se informa la cotizacion al cliente.
5. Si el cliente acepta, se programa el servicio y se genera la orden de trabajo (accion que no se puede deshacer): solo con el testigo y el si del cliente. Ids `COT-0001` y `OT-0001`, siguiendo la numeracion.
6. Si el cliente rechaza, se registra la cotizacion como rechazada y se cierra.

## Mensajes de error (siempre con que_hacer)

| codigo | cuando | mensaje | que_hacer |
| --- | --- | --- | --- |
| SERVICIO_NO_ENCONTRADO | ninguna palabra clave coincide | No encontre ese servicio en el tarifario. | Pedir al cliente que describa la falla de otra forma o derivar a una persona. |
| DESCUENTO_NO_PERMITIDO | pide descuento mayor al maximo | La politica no permite descuentos. | Informar la tarifa fija sin descuento. |
| MONTO_REQUIERE_APROBACION | total mayor a S/ 2000 | El total necesita aprobacion del jefe de taller. | Derivar a una persona. |
| TESTIGO_INVALIDO | testigo usado, vencido o inexistente | El testigo no es valido. | Volver a validar la cotizacion. |

## Cola de excepciones

Misma estructura que el proceso 1: id, fecha_hora, proceso, motivo, consulta_original y datos.
