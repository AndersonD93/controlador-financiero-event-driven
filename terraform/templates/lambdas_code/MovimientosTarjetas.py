import json
import boto3
import os
import uuid
from datetime import datetime

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_cuentas_validas,
    obtener_conceptos_validos
)

# =========================
# AWS clients
# =========================
dynamodb = boto3.resource("dynamodb")

# =========================
# DynamoDB table
# =========================
table = dynamodb.Table(os.getenv("historia_tarjetas_table"))

# =========================
# Headers HTTP
# =========================
HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
}


def lambda_handler(event, context):
    try:
        print(f"Evento recibido: {event}")

        body = json.loads(event["body"]) if "body" in event and event["body"] else event

        # =========================
        # Validación obligatoria
        # =========================
        required_fields = [
            "Franquicia",
            "Corte",
            "Valor",
            "FechaMovimiento",
            "DominioFinanciero",
            "Descripcion"
        ]

        missing = [f for f in required_fields if f not in body]
        if missing:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Campos obligatorios faltantes",
                    "missing_fields": missing
                })
            }

        dominio = body["DominioFinanciero"].strip().upper()
        franquicia = body["Franquicia"].strip().upper()
        concepto = body["Descripcion"].strip().upper()
        subconcepto = body.get("Subconcepto")

        # =========================
        # Carga catálogo unificado
        # =========================
        catalogo = cargar_catalogo()

        try:
            validar_dominio(catalogo, dominio)
        except ValueError as e:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({"message": str(e)})
            }

        # =========================
        # Validación franquicia (dinámica)
        # =========================
        try:
            tarjetas_validas = obtener_cuentas_validas(
                catalogo,
                dominio,
                tipo="TARJETA"
            )
        except ValueError as e:
            return {
                "statusCode": 500,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": str(e),
                    "dominio": dominio
                })
            }

        if franquicia not in tarjetas_validas:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Franquicia no permitida para el dominio",
                    "franquicia": franquicia,
                    "permitidas": tarjetas_validas
                })
            }

        # =========================
        # Validación concepto (dinámica)
        # =========================
        try:
            conceptos_validos = obtener_conceptos_validos(
                catalogo,
                dominio,
                "PROYECCION"
            )
        except ValueError as e:
            return {
                "statusCode": 500,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": str(e),
                    "dominio": dominio
                })
            }

        if concepto not in conceptos_validos:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Concepto no permitido según catálogo",
                    "concepto": concepto,
                    "permitidos": conceptos_validos
                })
            }

        # =========================
        # Construcción item
        # =========================
        item = {
            "trx_id": str(uuid.uuid4()),
            "franquicia": franquicia,
            "corte": body["Corte"],
            "valor": body["Valor"],
            "fechaMovimiento": body["FechaMovimiento"],
            "dominioFinanciero": dominio,
            "descripcion": concepto,
            "created_at": datetime.utcnow().isoformat()
        }

        if subconcepto:
            item["subconcepto"] = subconcepto.strip().upper()

        # =========================
        # Persistencia
        # =========================
        table.put_item(Item=item)

        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Movimiento de tarjeta registrado correctamente",
                "trx_id": item["trx_id"]
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Error interno al registrar movimiento de tarjeta",
                "error": str(e)
            })
        }