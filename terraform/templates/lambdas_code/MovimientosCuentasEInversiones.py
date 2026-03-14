import json
import boto3
import os
import uuid
from datetime import datetime

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_origenes_validos,
    obtener_conceptos_validos
)

# =========================
# AWS clients
# =========================
dynamodb = boto3.resource("dynamodb")

# =========================
# DynamoDB table
# =========================
table = dynamodb.Table(os.getenv("cuentas_alto_rendimiento_table"))

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
            "Cuenta",
            "Descripcion",
            "Valor",
            "FechaMovimiento",
            "Corte",
            "DominioFinanciero"
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

        # =========================
        # Normalización
        # =========================
        cuenta = body["Cuenta"].strip().upper()
        concepto = body["Descripcion"].strip().upper()
        dominio = body["DominioFinanciero"].strip().upper()
        subconcepto = body.get("Subconcepto")

        if subconcepto:
            subconcepto = subconcepto.strip().upper()

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
        # Validación CUENTA / ORIGEN
        # =========================
        cuentas_validas = obtener_origenes_validos(catalogo, dominio)

        if cuenta not in cuentas_validas:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Cuenta no permitida para el dominio",
                    "cuenta": cuenta,
                    "dominio": dominio,
                    "permitidas": cuentas_validas
                })
            }

        # =========================
        # Validación CONCEPTO
        # =========================
        if "PROYECCION" in catalogo[dominio]:
            bloque_validacion = "PROYECCION"
        else:
            bloque_validacion = "CAJA_ACTUAL"

        conceptos_validos = obtener_conceptos_validos(
            catalogo,
            dominio,
            bloque=bloque_validacion
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
            "cuenta": cuenta,
            "descripcion": concepto,
            "valor": body["Valor"],
            "fechaMovimiento": body["FechaMovimiento"],
            "corte": body["Corte"],
            "dominioFinanciero": dominio,
            "created_at": datetime.utcnow().isoformat()
        }

        if subconcepto:
            item["subconcepto"] = subconcepto

        table.put_item(Item=item)

        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Movimiento de cuenta de alto rendimiento registrado correctamente",
                "trx_id": item["trx_id"]
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Error interno al registrar movimiento",
                "error": str(e)
            })
        }