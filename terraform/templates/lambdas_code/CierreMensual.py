import boto3
import os
import logging
from datetime import datetime
from decimal import Decimal

from catalogo_financiero import cargar_catalogo

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table(os.getenv("flujo_caja_table"))


def obtener_cortes():
    hoy = datetime.utcnow()
    corte_actual = hoy.strftime("%Y-%m")

    if hoy.month == 12:
        corte_siguiente = f"{hoy.year + 1}-01"
    else:
        corte_siguiente = f"{hoy.year}-{hoy.month + 1:02d}"

    return corte_actual, corte_siguiente


def construir_sk(tipo, concepto, origen):
    return f"{tipo}#{concepto}#{origen}"


def lambda_handler(event, context):
    try:
        logger.info("INICIO CIERRE MENSUAL")

        # 1️⃣ Cargar catálogo desde el Layer (ya no desde SSM directo)
        catalogo = cargar_catalogo()

        corte_actual, corte_siguiente = obtener_cortes()

        for dominio, config in catalogo.items():
            logger.info(f"Procesando dominio: {dominio}")

            pk_actual = f"{dominio}#{corte_actual}"
            pk_siguiente = f"{dominio}#{corte_siguiente}"

            caja_actual = config.get("CAJA_ACTUAL", {})

            for tipo in ["CUENTA", "TARJETA"]:
                origenes = caja_actual.get(tipo, [])

                for origen in origenes:
                    try:
                        logger.info(
                            f"Liquidando {dominio} | {tipo} | {origen}"
                        )

                        sk_prefix = f"{tipo}#"

                        response = table.query(
                            KeyConditionExpression="#pk = :pk AND begins_with(#sk, :sk)",
                            ExpressionAttributeNames={
                                "#pk": "Dominio-Corte",
                                "#sk": "Tipo-Concepto"
                            },
                            ExpressionAttributeValues={
                                ":pk": pk_actual,
                                ":sk": sk_prefix
                            }
                        )

                        total = Decimal("0")

                        for item in response.get("Items", []):
                            if item.get("origen") == origen:
                                total += Decimal(str(item.get("valor", 0)))

                        if total == 0:
                            logger.info(
                                "Total en cero, no se crea SALDO_INICIAL"
                            )
                            continue

                        sk_saldo_inicial = construir_sk(
                            tipo,
                            "SALDO_INICIAL",
                            origen
                        )

                        table.put_item(
                            Item={
                                "Dominio-Corte": pk_siguiente,
                                "Tipo-Concepto": sk_saldo_inicial,
                                "tipo": tipo,
                                "bloque": "CAJA_ACTUAL",
                                "concepto": "SALDO_INICIAL",
                                "origen": origen,
                                "valor": total
                            }
                        )

                        logger.info(
                            f"SALDO_INICIAL creado ({dominio} | {tipo} | {origen}): {total}"
                        )

                    except Exception:
                        logger.error(
                            f"Error procesando {dominio} {tipo} {origen}",
                            exc_info=True
                        )

        logger.info("CIERRE MENSUAL FINALIZADO")
        return {"status": "OK"}

    except Exception:
        logger.critical(
            "ERROR GENERAL EN CIERRE MENSUAL",
            exc_info=True
        )
        raise