import json
import boto3
import os
import uuid
from datetime import datetime

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_conceptos_validos
)

# =========================
# AWS clients
# =========================
dynamodb = boto3.resource("dynamodb")

# =========================
# DynamoDB tables
# =========================
table_casa = dynamodb.Table(os.getenv("conceptos_fijos_table"))
table_personal = dynamodb.Table(os.getenv("conceptos_fijos_persona_table"))

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
        # Validación campos obligatorios
        # =========================
        required_fields = [
            "DominioFinanciero",
            "Concepto",
            "Valor",
            "Corte"
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
        concepto = body["Concepto"].strip().upper()
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
        # Selección de tabla
        # =========================
        if dominio == "CASA":
            table = table_casa
        elif dominio in ["PERSONAL", "AHORRO", "INVERSIONES"]:
            table = table_personal
        else:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "DominioFinanciero inválido"
                })
            }

        # =========================
        # Validación dinámica CONCEPTO
        # =========================

        conceptos_validos = obtener_conceptos_validos(
                catalogo,
                dominio,
                "PROYECCION"
        )

        if concepto not in conceptos_validos:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Concepto no permitido según el catálogo",
                    "concepto": concepto,
                    "dominio": dominio,
                    "permitidos": conceptos_validos
                })
            }

        # =========================
        # Construcción del item
        # =========================
        item = {
            "trx_id": str(uuid.uuid4()),
            "dominioFinanciero": dominio,
            "concepto": concepto,
            "valor": body["Valor"],
            "corte": body["Corte"],
            "created_at": datetime.utcnow().isoformat(),
            "origen_registro": "PROYECCION_MANUAL"
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
                "message": "Concepto registrado correctamente",
                "trx_id": item["trx_id"],
                "tabla_destino": table.name
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Error interno al registrar concepto",
                "error": str(e)
            })
        }