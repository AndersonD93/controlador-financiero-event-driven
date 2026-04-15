import json
import boto3
import os
from datetime import datetime


eventbridge = boto3.client("events")

EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]


def fecha_hoy():
    return datetime.utcnow().strftime("%Y-%m-%d")


def build_movimiento_general(state):

    concepto = state.get("concepto")

    # Caso especial INVERSIONES: el concepto se toma de la cuenta
    if state.get("dominio") == "INVERSIONES":
        concepto = state.get("cuenta")

    return {
        "Cuenta": state.get("cuenta"),
        "Descripcion": concepto,
        "Subconcepto": state.get("descripcion"),
        "Valor": int(state.get("valor")),
        "FechaMovimiento": fecha_hoy(),
        "Corte": state.get("corte"),
        "DominioFinanciero": state.get("dominio")
    }


def build_movimiento_tarjeta(state):

    return {
        "Franquicia": state.get("cuenta"),
        "Corte": state.get("corte"),
        "Valor": int(state.get("valor")),
        "FechaMovimiento": fecha_hoy(),
        "DominioFinanciero": state.get("dominio"),
        "Descripcion": state.get("concepto"),
        "Subconcepto": state.get("descripcion")
    }


def build_proyeccion(state):

    return {
        "Corte": state.get("corte"),
        "Valor": int(state.get("valor")),
        "FechaMovimiento": fecha_hoy(),
        "DominioFinanciero": state.get("dominio"),
        "Concepto": state.get("concepto"),
        "Subconcepto": state.get("descripcion")
    }


def build_transferencia(state):

    return {
        "Cuenta": state.get("cuenta"),
        "CuentaDestino": state.get("cuenta_destino"),
        "Descripcion": "TRANSFERENCIA",
        "Subconcepto": state.get("descripcion"),
        "Valor": int(state.get("valor")),
        "FechaMovimiento": fecha_hoy(),
        "Corte": state.get("corte"),
        "DominioFinanciero": state.get("dominio")
    }


def publish_event(event_type, payload, metadata):

    response = eventbridge.put_events(
        Entries=[
            {
                "Source": "app.financiero",
                "DetailType": event_type,
                "EventBusName": EVENT_BUS_NAME,
                "Detail": json.dumps({
                    "payload": payload,
                    "metadata": metadata
                })
            }
        ]
    )

    print("EventBridge response:", response)


def lambda_handler(event, context):

    print("Evento recibido en InterpretadorRouter:")
    print(json.dumps(event, indent=2))

    try:

        state = event.get("state")
        raw = event.get("raw")

        if not state:
            print("Evento no contiene state")
            return

        tipo = state.get("tipo_registro")

        metadata = {
            "user_id": raw.get("user", {}).get("id") if raw else None,
            "timestamp": datetime.utcnow().isoformat(),
            "channel_id": event.get("channel_id")
        }

        print("Tipo:", tipo)

        if tipo == "MOVIMIENTO_GENERAL":

            payload = build_movimiento_general(state)
            event_type = "movimiento.general.registrado"

        elif tipo == "MOVIMIENTO_TARJETA":

            payload = build_movimiento_tarjeta(state)
            event_type = "movimiento.tarjeta.registrado"

        elif tipo == "PROYECCION":

            payload = build_proyeccion(state)
            event_type = "proyeccion.registrado"

        elif tipo == "TRANSFERENCIA":

            payload = build_transferencia(state)
            event_type = "movimiento.general.registrado"

        else:
            raise Exception(f"Tipo de registro no soportado: {tipo}")

        print("Payload generado:")
        print(json.dumps(payload, indent=2))

        publish_event(event_type, payload, metadata)
        
        print("EVENTO ENVIADO A EVENTBRIDGE:")
        print(json.dumps({
            "Source": "app.financiero",
            "DetailType": event_type,
            "Detail": {
                "payload": payload,
                "metadata": metadata
            }
        }, indent=2))

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Evento publicado"})
        }
        

    except Exception as e:

        print("Error en InterpretadorRouter:", str(e))

        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
