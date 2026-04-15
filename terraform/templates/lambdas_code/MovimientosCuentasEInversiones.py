import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_origenes_validos,
    obtener_conceptos_validos,
    normalizar_evento
)

dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table(os.getenv("cuentas_alto_rendimiento_table"))

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
    return {
        "status": status,
        "body": body
    }


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
            "Cuenta",
            "Descripcion",
            "Valor",
            "FechaMovimiento",
            "Corte",
            "DominioFinanciero"
        ]

        missing = [f for f in required_fields if not payload.get(f)]

        if missing:
            error = {
                "message": "Campos obligatorios faltantes",
                "missing_fields": missing
            }
            print("❌", error)
            return build_response(source, 400, error)

        cuenta = payload["Cuenta"].strip().upper()
        concepto = payload["Descripcion"].strip().upper()
        dominio = payload["DominioFinanciero"].strip().upper()
        subconcepto = payload.get("Subconcepto")
        cuenta_destino = payload.get("CuentaDestino")

        if subconcepto:
            subconcepto = subconcepto.strip().upper()

        if cuenta_destino:
            cuenta_destino = cuenta_destino.strip().upper()

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
            cuentas_validas = obtener_origenes_validos(catalogo, dominio)
        except ValueError as e:
            return build_response(source, 500, {
                "message": str(e),
                "dominio": dominio
            })

        if cuenta not in cuentas_validas:
            return build_response(source, 400, {
                "message": "Cuenta no permitida para el dominio",
                "cuenta": cuenta,
                "dominio": dominio,
                "permitidas": cuentas_validas
            })

        bloque_validacion = "PROYECCION" if "PROYECCION" in catalogo[dominio] else "CAJA_ACTUAL"

        try:
            conceptos_validos = obtener_conceptos_validos(
                catalogo,
                dominio,
                bloque=bloque_validacion
            )
        except ValueError as e:
            return build_response(source, 500, {
                "message": str(e),
                "dominio": dominio
            })

        if concepto not in conceptos_validos:
            return build_response(source, 400, {
                "message": "Concepto no permitido según el catálogo",
                "concepto": concepto,
                "dominio": dominio,
                "permitidos": conceptos_validos
            })

        # Validar cuenta_destino cuando el concepto es TRANSFERENCIA
        if concepto == "TRANSFERENCIA":
            if not cuenta_destino:
                return build_response(source, 400, {
                    "message": "CuentaDestino es obligatorio para transferencias"
                })
            if cuenta_destino not in cuentas_validas:
                return build_response(source, 400, {
                    "message": "CuentaDestino no permitida para el dominio",
                    "cuenta_destino": cuenta_destino,
                    "permitidas": cuentas_validas
                })
            if cuenta_destino == cuenta:
                return build_response(source, 400, {
                    "message": "CuentaDestino no puede ser igual a la cuenta origen"
                })

        item = {
            "trx_id": str(uuid.uuid4()),
            "cuenta": cuenta,
            "descripcion": concepto,
            "valor": valor,
            "fechaMovimiento": payload["FechaMovimiento"],
            "corte": payload["Corte"],
            "dominioFinanciero": dominio,
            "created_at": datetime.utcnow().isoformat(),
            "user_id": metadata.get("user_id")
        }

        if subconcepto:
            item["subconcepto"] = subconcepto

        if cuenta_destino:
            item["cuentaDestino"] = cuenta_destino

        print("Item a guardar:")
        print(json.dumps(item, indent=2, default=str))

        table.put_item(Item=item)
        if source == "eventbridge":
            publicar_evento("movimiento.cuenta.confirmado", item, source,channel_id=metadata.get("channel_id"))

        response = {
            "message": "Movimiento de cuenta de alto rendimiento registrado correctamente",
            "trx_id": item["trx_id"]
        }

        return build_response(source, 200, response)

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Error interno al registrar movimiento",
                "error": str(e)
            })
        }