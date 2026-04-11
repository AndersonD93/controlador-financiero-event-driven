import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_cuentas_validas,
    obtener_conceptos_validos,
    normalizar_evento
)

dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table(os.getenv("historia_tarjetas_table"))

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
}

def build_response(source, status, body):
    if source == "apigateway":
        return {
            "statusCode": status,
            "headers": HEADERS,
            "body": json.dumps(body)
        }
    return body

def publicar_evento(detail_type, item, source, channel_id=None):
    try:
        eventbridge = boto3.client("events")

        eventbridge.put_events(Entries=[{
            "Source": "app.financiero",
            "DetailType": detail_type,
            "Detail": json.dumps({
                "trx_id":            item["trx_id"],
                "dominioFinanciero": item.get("dominioFinanciero"),
                "concepto":          item.get("concepto") or item.get("descripcion"),
                "descripcion":       item.get("descripcion"),
                "valor":             str(item.get("valor")),
                "corte":             item.get("corte"),
                "user_id":           item.get("user_id"),
                "source":            source,
                "channel_id":        channel_id
            }),
            "EventBusName": os.getenv("EVENT_BUS_NAME")
        }])

        print(f"Evento publicado: {detail_type}")

    except Exception as e:
        # No bloqueamos la respuesta principal si falla la notificación
        print(f"Error publicando evento en EventBridge: {str(e)}")
        

def lambda_handler(event, context):
    try:
        print("EVENTO CRUDO:")
        print(json.dumps(event, indent=2))

        payload, metadata, source = normalizar_evento(event)

        if not isinstance(payload, dict):
            print("Payload inválido, se fuerza a {}")
            payload = {}

        metadata = metadata or {}

        print("Payload normalizado:")
        print(json.dumps(payload, indent=2))

        print("Metadata:")
        print(json.dumps(metadata, indent=2))

        print("Source:", source)

        required_fields = [
            "Franquicia",
            "Corte",
            "Valor",
            "FechaMovimiento",
            "DominioFinanciero",
            "Descripcion"
        ]

        missing = [f for f in required_fields if not payload.get(f)]

        if missing:
            error = {
                "message": "Campos obligatorios faltantes",
                "missing_fields": missing
            }
            print("❌", error)
            return build_response(source, 400, error)

        dominio = payload["DominioFinanciero"].strip().upper()
        franquicia = payload["Franquicia"].strip().upper()
        concepto = payload["Descripcion"].strip().upper()
        subconcepto = payload.get("Subconcepto")

        try:
            valor = Decimal(str(payload["Valor"]))
        except Exception:
            return build_response(source, 400, {
                "message": "Valor debe ser numérico",
                "valor_recibido": payload["Valor"]
            })

        catalogo = cargar_catalogo()

        try:
            validar_dominio(catalogo, dominio)
        except ValueError as e:
            return build_response(source, 400, {"message": str(e)})

        try:
            tarjetas_validas = obtener_cuentas_validas(
                catalogo,
                dominio,
                tipo="TARJETA"
            )
        except ValueError as e:
            return build_response(source, 500, {
                "message": str(e),
                "dominio": dominio
            })

        if franquicia not in tarjetas_validas:
            return build_response(source, 400, {
                "message": "Franquicia no permitida para el dominio",
                "franquicia": franquicia,
                "permitidas": tarjetas_validas
            })

        try:
            conceptos_validos = obtener_conceptos_validos(
                catalogo,
                dominio,
                "PROYECCION"
            )
        except ValueError as e:
            return build_response(source, 500, {
                "message": str(e),
                "dominio": dominio
            })

        if concepto not in conceptos_validos:
            return build_response(source, 400, {
                "message": "Concepto no permitido según catálogo",
                "concepto": concepto,
                "permitidos": conceptos_validos
            })

        item = {
            "trx_id": str(uuid.uuid4()),
            "franquicia": franquicia,
            "corte": payload["Corte"],
            "valor": valor,
            "fechaMovimiento": payload["FechaMovimiento"],
            "dominioFinanciero": dominio,
            "descripcion": concepto,
            "created_at": datetime.utcnow().isoformat(),
            "user_id": metadata.get("user_id")
        }

        if subconcepto:
            item["subconcepto"] = subconcepto.strip().upper()

        print("Item a guardar:")
        print(json.dumps(item, indent=2, default=str))

        table.put_item(Item=item)
        if source == "eventbridge":
            publicar_evento("movimiento.tarjeta.confirmado", item, source, channel_id=metadata.get("channel_id"))

        response = {
            "message": "Movimiento de tarjeta registrado correctamente",
            "trx_id": item["trx_id"]
        }

        return build_response(source, 200, response)

    except Exception as e:
        print("Error:", str(e))
        return {
            "statusCode": 500,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Error interno al registrar movimiento de tarjeta",
                "error": str(e)
            })
        }