import json
import boto3
import os
import uuid
import logging
from datetime import datetime

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_conceptos_validos
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# =========================
# AWS Clients
# =========================
dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

# =========================
# Tables
# =========================
table_casa = dynamodb.Table(os.getenv("conceptos_fijos_table"))
table_personal = dynamodb.Table(os.getenv("conceptos_fijos_persona_table"))

# =========================
# Parameter Store
# =========================
PROYECCIONES_PARAM = "/flujo-caja/proyecciones-fijas"

# =========================
# Helpers
# =========================

def cargar_proyecciones():
    response = ssm.get_parameter(
        Name=PROYECCIONES_PARAM,
        WithDecryption=True
    )
    return json.loads(response["Parameter"]["Value"])


def calcular_corte_ejecucion():
    """
    Retorna el corte basado en el mes en que se ejecuta la Lambda.
    Diseñada para ejecutarse el día 1 de cada mes (cron 0 0 1 * ? *)
    """
    hoy = datetime.utcnow()
    return hoy.strftime("%Y-%m")


def seleccionar_tabla(dominio):
    if dominio == "CASA":
        return table_casa
    elif dominio in ["PERSONAL", "AHORRO", "INVERSIONES"]:
        return table_personal
    else:
        raise ValueError(f"Dominio no soportado: {dominio}")


# =========================
# Lambda Handler
# =========================

def lambda_handler(event, context):
    try:
        logger.info(f"Evento recibido: {event}")

        # Permite ejecución vía API o EventBridge
        body = {}

        if "body" in event and event["body"]:
            body = json.loads(event["body"])
        elif isinstance(event, dict):
            body = event

        # =========================
        # Determinar corte
        # =========================
        corte = body.get("Corte")

        if corte:
            logger.info(f"Corte recibido manualmente: {corte}")
        else:
            corte = calcular_corte_ejecucion()
            logger.info(f"Corte determinado por fecha de ejecución: {corte}")

        # =========================
        # Cargar datos
        # =========================
        catalogo = cargar_catalogo()
        proyecciones = cargar_proyecciones()

        registros_creados = []

        # =========================
        # Procesamiento principal
        # =========================
        for dominio, conceptos in proyecciones.items():

            dominio = dominio.strip().upper()

            # Validar dominio contra catálogo
            validar_dominio(catalogo, dominio)

            try:
                conceptos_validos = obtener_conceptos_validos(
                    catalogo,
                    dominio,
                    "PROYECCION"
                )
            except ValueError:
                logger.info(f"Dominio {dominio} no tiene bloque PROYECCION. Se omite.")
                continue

            table = seleccionar_tabla(dominio)

            for concepto, valor in conceptos.items():

                concepto = concepto.strip().upper()

                # Validar concepto contra catálogo
                if concepto not in conceptos_validos:
                    logger.warning(
                        f"Concepto inválido omitido: {dominio} - {concepto}"
                    )
                    continue

                item = {
                    "trx_id": str(uuid.uuid4()),
                    "dominioFinanciero": dominio,
                    "concepto": concepto,
                    "valor": valor,
                    "corte": corte,
                    "created_at": datetime.utcnow().isoformat(),
                    "origen_registro": "PROYECCION_AUTOMATICA"
                }

                table.put_item(Item=item)

                registros_creados.append({
                    "dominio": dominio,
                    "concepto": concepto,
                    "valor": valor
                })

                logger.info(
                    f"Insertado: {dominio} - {concepto} - {valor}"
                )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Proyecciones contabilizadas correctamente",
                "corte": corte,
                "registros_insertados": registros_creados
            })
        }

    except Exception as e:
        logger.error("Error en contabilización automática", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error interno",
                "error": str(e)
            })
        }