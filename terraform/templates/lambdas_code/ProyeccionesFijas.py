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
    Retorna una lista de 3 cortes a proyectar hacia adelante.
    El punto de inicio es el mes SIGUIENTE al actual (o al corte_base recibido),
    ya que el mes actual ya fue procesado por el CierreMensual.

    Ejemplo ejecutando en mayo 2026: ['2026-06', '2026-07', '2026-08']
    Si se recibe corte_base='2026-05', el inicio es '2026-06'.
    """
    if corte_base:
        fecha_base = datetime.strptime(corte_base, "%Y-%m")
    else:
        hoy = datetime.utcnow()
        fecha_base = hoy.replace(day=1)

    # Avanzar un mes para no pisar el mes actual
    mes_inicio = fecha_base.month + 1
    anio_inicio = fecha_base.year + (mes_inicio - 1) // 12
    mes_inicio = ((mes_inicio - 1) % 12) + 1

    cortes = []
    for i in range(MESES_PROYECCION):
        mes = mes_inicio + i
        anio = anio_inicio + (mes - 1) // 12
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

    IMPORTANTE: No usar Limit aquí. En DynamoDB, Limit acota los ítems *evaluados*
    antes de aplicar el FilterExpression, no los resultados finales. Con Limit=1
    se puede evaluar solo un ítem que no tenga PROYECCION_AUTOMATICA y retornar
    False aunque el corte ya esté proyectado (falso negativo → sobreescritura).
    """
    last_evaluated_key = None

    while True:
        query_kwargs = {
            "IndexName": "gsi-dominio-corte",
            "KeyConditionExpression": (
                Key("dominioFinanciero").eq(dominio) &
                Key("corte").eq(corte)
            ),
            "FilterExpression": Attr("origen_registro").eq(ORIGEN_AUTOMATICO),
        }

        if last_evaluated_key:
            query_kwargs["ExclusiveStartKey"] = last_evaluated_key

        response = table.query(**query_kwargs)

        if response["Count"] > 0:
            return True

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return False


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