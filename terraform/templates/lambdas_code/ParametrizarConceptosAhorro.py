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
# DynamoDB tables
# =========================
table_casa = dynamodb.Table(os.getenv("conceptos_fijos_table"))
table_personal = dynamodb.Table(os.getenv("conceptos_fijos_persona_table"))

# =========================
# Parameter Store
# =========================
CATALOGO_PARAM = "/flujo-caja/catalogo-conceptos"

# Cache globals (persisten entre invocaciones warm)
CATALOGO_CACHE = None
CATALOGO_CACHE_TS = 0
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
# Carga de catálogo con cache
# =========================
def cargar_catalogo():
    global CATALOGO_CACHE, CATALOGO_CACHE_TS

    now = time.time()

    # Cache válido
    if CATALOGO_CACHE and (now - CATALOGO_CACHE_TS) < CATALOGO_TTL_SECONDS:
        return CATALOGO_CACHE

    # Cold start o TTL vencido
    try:
        print("Cargando catálogo de conceptos desde Parameter Store")
        response = ssm.get_parameter(
            Name=CATALOGO_PARAM,
            WithDecryption=False
        )

        CATALOGO_CACHE = json.loads(response["Parameter"]["Value"])
        CATALOGO_CACHE_TS = now

        return CATALOGO_CACHE

    except ClientError as e:
        raise Exception(f"No se pudo cargar el catálogo de conceptos: {str(e)}")

# =========================
# Lambda handler
# =========================
def lambda_handler(event, context):
    try:
        print(f"Evento recibido: {event}")

        # Soporte API Gateway y llamada directa
        body = json.loads(event["body"]) if "body" in event and event["body"] else event
        print(f"Body procesado: {body}")

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
        # Selección de tabla
        # =========================
        if dominio == "CASA":
            table = table_casa
        elif dominio in ["PERSONAL","AHORRO"]:
            table = table_personal
        else:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "DominioFinanciero inválido. Valores permitidos: CASA, PERSONAL, AHORRO"
                })
            }

        # =========================
        # Validación contra catálogo (cacheado)
        # =========================
        catalogo = cargar_catalogo()

        try:
            conceptos_validos = catalogo[dominio]["PROYECCION"]["GASTOS"]
        except KeyError:
            return {
                "statusCode": 500,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Configuración inválida del catálogo para el dominio",
                    "dominio": dominio
                })
            }

        if concepto not in conceptos_validos:
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Concepto no permitido según el catálogo",
                    "concepto": concepto,
                    "dominio": dominio
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
            "created_at": datetime.utcnow().isoformat()
        }

        if subconcepto:
            item["subconcepto"] = subconcepto.strip()

        # =========================
        # Persistencia
        # =========================
        table.put_item(Item=item)

        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Concepto de ahorro registrado correctamente",
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
                "message": "Error interno al registrar concepto de ahorro",
                "error": str(e)
            })
        }
