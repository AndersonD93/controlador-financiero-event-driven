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
table = dynamodb.Table(os.getenv("cuentas_alto_rendimiento_table"))

# =========================
# Parameter Store
# =========================
CATALOGO_CUENTAS_PARAM = "/flujo-caja/catalogo-cuentas"
CATALOGO_CONCEPTOS_PARAM = "/flujo-caja/catalogo-conceptos"

# =========================
# Cache independientes
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

    try:
        print("Cargando catálogo de cuentas desde Parameter Store")
        response = ssm.get_parameter(
            Name=CATALOGO_CUENTAS_PARAM,
            WithDecryption=False
        )

        CATALOGO_CUENTAS_CACHE = json.loads(response["Parameter"]["Value"])
        CATALOGO_CUENTAS_TS = now
        return CATALOGO_CUENTAS_CACHE

    except ClientError as e:
        raise Exception(f"No se pudo cargar el catálogo de cuentas: {str(e)}")

# =========================
# Carga catálogo conceptos
# =========================
def cargar_catalogo_conceptos():
    global CATALOGO_CONCEPTOS_CACHE, CATALOGO_CONCEPTOS_TS
    now = time.time()

    if CATALOGO_CONCEPTOS_CACHE and (now - CATALOGO_CONCEPTOS_TS) < CATALOGO_TTL_SECONDS:
        return CATALOGO_CONCEPTOS_CACHE

    try:
        print("Cargando catálogo de conceptos desde Parameter Store")
        response = ssm.get_parameter(
            Name=CATALOGO_CONCEPTOS_PARAM,
            WithDecryption=False
        )

        CATALOGO_CONCEPTOS_CACHE = json.loads(response["Parameter"]["Value"])
        CATALOGO_CONCEPTOS_TS = now
        return CATALOGO_CONCEPTOS_CACHE

    except ClientError as e:
        raise Exception(f"No se pudo cargar el catálogo de conceptos: {str(e)}")

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
        # Validación CUENTA
        # =========================
        catalogo_cuentas = cargar_catalogo_cuentas()

        try:
            cuentas_validas = catalogo_cuentas[dominio]["CUENTAS"]
        except KeyError:
            return {
                "statusCode": 500,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Configuración inválida del catálogo de cuentas",
                    "dominio": dominio
                })
            }

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
        catalogo_conceptos = cargar_catalogo_conceptos()

        try:
            conceptos_validos = catalogo_conceptos[dominio]["PROYECCION"]["GASTOS"]
        except KeyError:
            return {
                "statusCode": 500,
                "headers": HEADERS,
                "body": json.dumps({
                    "message": "Configuración inválida del catálogo de conceptos",
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

        # =========================
        # Persistencia
        # =========================
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
