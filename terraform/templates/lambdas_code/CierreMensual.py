import boto3
import json
import os
import logging
from datetime import datetime
from decimal import Decimal
from botocore.exceptions import ClientError

from catalogo_financiero import cargar_catalogo

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

table = dynamodb.Table(os.getenv("flujo_caja_table"))

CONCEPTOS_PERSISTENTES_PARAM = "/flujo-caja/conceptos-persistentes-cierre"


def obtener_cortes():
    hoy = datetime.utcnow()

    # El cierre se ejecuta el día 1 del mes actual, liquidando el mes anterior
    if hoy.month == 1:
        anio_anterior = hoy.year - 1
        mes_anterior = 12
    else:
        anio_anterior = hoy.year
        mes_anterior = hoy.month - 1

    corte_actual = f"{anio_anterior}-{mes_anterior:02d}"
    corte_siguiente = hoy.strftime("%Y-%m")

    return corte_actual, corte_siguiente


def construir_sk(tipo, concepto, origen):
    if tipo in ["CUENTA", "TARJETA"] and origen:
        return f"{tipo}#{concepto}#{origen}"
    return f"{tipo}#{concepto}"


def cargar_conceptos_persistentes():
    try:
        response = ssm.get_parameter(Name=CONCEPTOS_PERSISTENTES_PARAM)
        return json.loads(response["Parameter"]["Value"])
    except ClientError as e:
        logger.warning(f"No se pudo cargar conceptos persistentes: {str(e)}. Se asume vacío.")
        return {}


def cerrar_proyecciones(pk_actual, pk_siguiente, dominio, conceptos_persistentes_dominio):
    """
    Para el corte actual de un dominio:
    - Consulta todos los ítems de bloque PROYECCION
    - Los que están en conceptos_persistentes_dominio: los traslada al siguiente corte
    - El resto: los elimina (delete_item)
    """
    response = table.query(
        KeyConditionExpression="#pk = :pk AND begins_with(#sk, :sk)",
        ExpressionAttributeNames={
            "#pk": "Dominio-Corte",
            "#sk": "Tipo-Concepto"
        },
        ExpressionAttributeValues={
            ":pk": pk_actual,
            ":sk": "GASTO#"
        }
    )

    items = response.get("Items", [])
    logger.info(f"[{dominio}] Proyecciones encontradas en {pk_actual}: {len(items)}")

    for item in items:
        concepto = item.get("concepto", "")
        sk = item["Tipo-Concepto"]

        if concepto in conceptos_persistentes_dominio:
            valor = item.get("valor", Decimal("0"))

            if valor != 0:
                logger.info(f"[{dominio}] Trasladando concepto persistente '{concepto}' → {pk_siguiente} (valor: {valor})")

                table.update_item(
                    Key={
                        "Dominio-Corte": pk_siguiente,
                        "Tipo-Concepto": sk
                    },
                    UpdateExpression="ADD #v :inc SET tipo = :t, bloque = :b, concepto = :c",
                    ExpressionAttributeNames={"#v": "valor"},
                    ExpressionAttributeValues={
                        ":inc": valor,
                        ":t": item.get("tipo", "GASTO"),
                        ":b": "PROYECCION",
                        ":c": concepto
                    }
                )
            else:
                logger.info(f"[{dominio}] Concepto persistente '{concepto}' en cero, no se traslada")
        else:
            logger.info(f"[{dominio}] Eliminando proyección '{concepto}' del corte {pk_actual}")

            table.delete_item(
                Key={
                    "Dominio-Corte": pk_actual,
                    "Tipo-Concepto": sk
                }
            )


def lambda_handler(event, context):
    try:
        logger.info("INICIO CIERRE MENSUAL")

        catalogo = cargar_catalogo()
        conceptos_persistentes = cargar_conceptos_persistentes()

        corte_actual, corte_siguiente = obtener_cortes()
        logger.info(f"Corte actual: {corte_actual} → Corte siguiente: {corte_siguiente}")

        for dominio, config in catalogo.items():
            logger.info(f"Procesando dominio: {dominio}")

            pk_actual = f"{dominio}#{corte_actual}"
            pk_siguiente = f"{dominio}#{corte_siguiente}"

            caja_actual = config.get("CAJA_ACTUAL", {})

            # 1. Trasladar saldos de CAJA_ACTUAL al siguiente corte
            for tipo in ["CUENTA", "TARJETA"]:
                origenes = caja_actual.get(tipo, [])

                for origen in origenes:
                    try:
                        logger.info(f"Liquidando {dominio} | {tipo} | {origen}")

                        response = table.query(
                            KeyConditionExpression="#pk = :pk AND begins_with(#sk, :sk)",
                            ExpressionAttributeNames={
                                "#pk": "Dominio-Corte",
                                "#sk": "Tipo-Concepto"
                            },
                            ExpressionAttributeValues={
                                ":pk": pk_actual,
                                ":sk": f"{tipo}#"
                            }
                        )

                        total = Decimal("0")

                        for item in response.get("Items", []):
                            if item.get("origen") == origen:
                                total += Decimal(str(item.get("valor", 0)))

                        if total == 0:
                            logger.info("Total en cero, no se crea SALDO_INICIAL")
                            continue

                        sk_saldo_inicial = construir_sk(tipo, "SALDO_INICIAL", origen)

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

                        logger.info(f"SALDO_INICIAL creado ({dominio} | {tipo} | {origen}): {total}")

                    except Exception:
                        logger.error(f"Error liquidando {dominio} {tipo} {origen}", exc_info=True)

            # 2. Cerrar proyecciones del corte actual
            try:
                persistentes_dominio = conceptos_persistentes.get(dominio, [])
                cerrar_proyecciones(pk_actual, pk_siguiente, dominio, persistentes_dominio)
            except Exception:
                logger.error(f"Error cerrando proyecciones de {dominio}", exc_info=True)

        logger.info("CIERRE MENSUAL FINALIZADO")
        return {"status": "OK"}

    except Exception:
        logger.critical("ERROR GENERAL EN CIERRE MENSUAL", exc_info=True)
        raise
