import json
import boto3
import os
import uuid
import time
from datetime import datetime
from botocore.exceptions import ClientError

# =========================
# AWS clients
# =========================
dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

# =========================
# DynamoDB table
# =========================
table = dynamodb.Table(os.getenv("historia_tarjetas_table"))

# =========================
# Parameter Store paths
# =========================
CATALOGO_CUENTAS_PARAM = "/flujo-caja/catalogo-cuentas"
CATALOGO_CONCEPTOS_PARAM = "/flujo-caja/catalogo-conceptos"

# =========================
# Cache globals
# =========================
CATALOGO_CUENTAS_CACHE = None
CATALOGO_CUENTAS_TS = 0

CATALOGO_CONCEPTOS_CACHE = None
CATALOGO_CONCEPTOS_TS = 0

CATALOGO_TTL_SECONDS = 600  # 10 minutos

# =========================
# Headers HTTP
# =========================
HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
}

# =========================
# Carga catálogo cuentas
# =========================
def cargar_catalogo_cuentas():
    global CATALOGO_CUENTAS_CACHE, CATALOGO_CUENTAS_TS

    now = time.time()
    if CATALOGO_CUENTAS_CACHE and (now - CATALOGO_CUENTAS_TS) < CATALOGO_TTL_SECONDS:
        return CATALOGO_CUENTAS_CACHE

    response = ssm.get_parameter(
        Name=CATALOGO_CUENTAS_PARAM,
        WithDecryption=False
    )

    CATALOGO_CUENTAS_CACHE = json.loads(response["Parameter"]["Value"])
    CATALOGO_CUENTAS_TS = now
    return CATALOGO_CUENTAS_CACHE


# =========================
# Carga catálogo conceptos
# =========================
def cargar_catalogo_conceptos():
    global CATALOGO_CONCEPTOS_CACHE, CATALOGO_CONCEPTOS_TS

    now = time.time()
    if CATALOGO_CONCEPTOS_CACHE and (now - CATALOGO_CONCEPTOS_TS) < CATALOGO_TTL_SECONDS:
        return CATALOGO_CONCEPTOS_CACHE

    response = ssm.get_parameter(
        Name=CATALOGO_CONCEPTOS_PARAM,
        WithDecryption=False
    )

    CATALOGO_CONCEPTOS_CACHE = json.loads(response["Parameter"]["Value"])
    CATALOGO_CONCEPTOS_TS = now
    return CATALOGO_CONCEPTOS_CACHE


# =========================
# Lambda handler
# =========================
def lambda_handler(event, context):
    try:
        print(f"Evento recibido: {event}")

        body = json.loads(event["body"]) if "body" in event and event["body"] else event
        print(f"Body procesado: {body}")

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
        # Validación franquicia
        # =========================
        catalogo_cuentas = cargar_catalogo_cuentas()

        try:
            tarjetas_validas = catalogo_cuentas[dominio]["TARJETAS"]
        except KeyError:
            return {
                "statusCode": 500,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Configuración inválida del catálogo de cuentas",
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
        # Validación concepto
        # =========================
        catalogo_conceptos = cargar_catalogo_conceptos()

        try:
            conceptos_validos = catalogo_conceptos[dominio]["PROYECCION"]["GASTOS"]
        except KeyError:
            return {
                "statusCode": 500,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Configuración inválida del catálogo de conceptos",
                    "dominio": dominio,
                    "bloque": "CAJA_ACTUAL",
                    "tipo": "TARJETA"
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
