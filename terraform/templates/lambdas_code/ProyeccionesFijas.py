import json
import boto3
import os
import uuid
import logging
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_conceptos_validos
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

table_casa = dynamodb.Table(os.getenv("conceptos_fijos_table"))
table_personal = dynamodb.Table(os.getenv("conceptos_fijos_persona_table"))

PROYECCIONES_PARAM = "/flujo-caja/proyecciones-fijas"

ORIGEN_AUTOMATICO = "PROYECCION_AUTOMATICA"
MESES_PROYECCION = 3  # Mes actual + 2 siguientes


def cargar_proyecciones():
    response = ssm.get_parameter(
        Name=PROYECCIONES_PARAM,
        WithDecryption=True
    )
    return json.loads(response["Parameter"]["Value"])


def calcular_cortes(corte_base=None):
    """
    Retorna una lista de 3 cortes: el mes actual + los 2 siguientes.
    Formato: ['2026-05', '2026-06', '2026-07']
    Si se recibe corte_base explícito, lo usa como punto de inicio.
    Si no, usa el mes actual (fecha UTC).
    """
    if corte_base:
        fecha_inicio = datetime.strptime(corte_base, "%Y-%m")
    else:
        hoy = datetime.utcnow()
        fecha_inicio = hoy.replace(day=1)

    cortes = []
    for i in range(MESES_PROYECCION):
        mes = fecha_inicio.month + i
        anio = fecha_inicio.year + (mes - 1) // 12
        mes = ((mes - 1) % 12) + 1
        cortes.append(f"{anio}-{mes:02d}")

    return cortes


def seleccionar_tabla(dominio):
    if dominio == "CASA":
        return table_casa
    elif dominio in ["PERSONAL", "AHORRO", "INVERSIONES"]:
        return table_personal
    else:
        raise ValueError(f"Dominio no soportado: {dominio}")


def corte_ya_proyectado_automaticamente(table, dominio, corte):
    """
    Verifica si ya existe al menos un registro con origen_registro = PROYECCION_AUTOMATICA
    para el dominio y corte dados, usando el GSI gsi-dominio-corte
    (hash_key: dominioFinanciero, range_key: corte).
    Retorna True si el corte ya fue proyectado automáticamente, False si no.
    """
    response = table.query(
        IndexName="gsi-dominio-corte",
        KeyConditionExpression=(
            Key("dominioFinanciero").eq(dominio) &
            Key("corte").eq(corte)
        ),
        FilterExpression=Attr("origen_registro").eq(ORIGEN_AUTOMATICO),
        Limit=1
    )
    return response["Count"] > 0


def lambda_handler(event, context):
    try:
        logger.info(f"Evento recibido: {event}")

        body = {}
        if "body" in event and event["body"]:
            body = json.loads(event["body"])
        elif isinstance(event, dict):
            body = event

        corte_base = body.get("Corte")  # Opcional: fuerza un mes de inicio distinto
        cortes = calcular_cortes(corte_base)

        logger.info(f"Cortes a evaluar: {cortes}")

        catalogo = cargar_catalogo()
        proyecciones = cargar_proyecciones()

        resultado_por_corte = {}

        for corte in cortes:

            resultado_por_corte[corte] = {
                "omitidos_por_duplicado": [],
                "insertados": []
            }

            for dominio, conceptos in proyecciones.items():

                dominio = dominio.strip().upper()
                validar_dominio(catalogo, dominio)

                try:
                    conceptos_validos = obtener_conceptos_validos(
                        catalogo,
                        dominio,
                        "PROYECCION"
                    )
                except ValueError:
                    logger.info(f"[{corte}] Dominio {dominio} sin bloque PROYECCION. Se omite.")
                    continue

                table = seleccionar_tabla(dominio)

                # ─── Idempotencia por corte + dominio ───
                if corte_ya_proyectado_automaticamente(table, dominio, corte):
                    logger.info(
                        f"[{corte}] Dominio {dominio} ya tiene proyección automática. Se omite."
                    )
                    resultado_por_corte[corte]["omitidos_por_duplicado"].append(dominio)
                    continue

                for concepto, valor in conceptos.items():

                    concepto = concepto.strip().upper()

                    if concepto not in conceptos_validos:
                        logger.warning(f"[{corte}] Concepto inválido omitido: {dominio} - {concepto}")
                        continue

                    item = {
                        "trx_id": str(uuid.uuid4()),
                        "dominioFinanciero": dominio,
                        "concepto": concepto,
                        "valor": valor,
                        "corte": corte,
                        "created_at": datetime.utcnow().isoformat(),
                        "origen_registro": ORIGEN_AUTOMATICO
                    }

                    table.put_item(Item=item)

                    resultado_por_corte[corte]["insertados"].append({
                        "dominio": dominio,
                        "concepto": concepto,
                        "valor": valor
                    })

                    logger.info(f"[{corte}] Insertado: {dominio} - {concepto} - {valor}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Proyecciones procesadas correctamente",
                "cortes_evaluados": cortes,
                "resultado": resultado_por_corte
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