import json
import boto3
import os
import time
from decimal import Decimal
from botocore.exceptions import ClientError

# ========================
# AWS Clients
# ========================
dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

table = dynamodb.Table(os.getenv("flujo_caja_table"))

# ========================
# Parámetro de reglas
# ========================
REGLAS_PARAM = "/flujo-caja/reglas-compensacion"

# Cache en memoria (cold-start aware)
REGLAS_CACHE = None
REGLAS_CACHE_TS = 0
REGLAS_TTL = 300  # 5 minutos

# ========================
# Contexto por tabla origen
# ========================
TABLE_CONTEXT_MAP = {
    "HistoriaCuentasAltoRendimiento_modules_IAC": {
        "tipo": "CUENTA",
        "bloque": "CAJA_ACTUAL",
        "origen_field": "cuenta"
    },
    "HistorialTarjetas_modules_IAC": {
        "tipo": "TARJETA",
        "bloque": "CAJA_ACTUAL",
        "origen_field": "franquicia"
    },
    "ConceptosFijosObligaciones_modules_IAC": {
        "tipo": "GASTO",
        "bloque": "PROYECCION"
    },
    "ConceptosFijosPersonal_modules_IAC": {
        "tipo": "GASTO",
        "bloque": "PROYECCION"
    }
}

# ========================
# Carga de reglas (cache)
# ========================
def cargar_reglas():
    global REGLAS_CACHE, REGLAS_CACHE_TS

    now = time.time()

    if REGLAS_CACHE and (now - REGLAS_CACHE_TS) < REGLAS_TTL:
        print("CHECKPOINT R0 - Reglas desde cache")
        return REGLAS_CACHE

    try:
        response = ssm.get_parameter(Name=REGLAS_PARAM)
        reglas = json.loads(response["Parameter"]["Value"]).get("reglas", [])
        REGLAS_CACHE = reglas
        REGLAS_CACHE_TS = now
        print(f"CHECKPOINT R1 - Reglas cargadas desde SSM ({len(reglas)})")
        return reglas
    except ClientError as e:
        raise Exception(f"Error cargando reglas: {str(e)}")

# ========================
# Evaluador de reglas
# ========================
def regla_aplica(regla, contexto):
    print(f"→ Evaluando regla {regla.get('id')}")

    # -------------------------
    # Regla activa
    # -------------------------
    if not regla.get("activo"):
        print("- Rechazada: regla inactiva")
        return False

    # -------------------------
    # Tipo origen
    # -------------------------
    if contexto["tipo"] not in regla["tipos_origen"]:
        print("- Rechazada: tipo no coincide")
        return False

    # -------------------------
    # Bloque origen
    # -------------------------
    if contexto["bloque"] != regla["bloque_origen"]:
        print("- Rechazada: bloque no coincide")
        return False

    # -------------------------
    # Exclusión por concepto (NUEVO)
    # -------------------------
    concepto = contexto.get("concepto")

    if "excluir_conceptos" in regla:
        if concepto in regla["excluir_conceptos"]:
            print(f"- Rechazada: concepto excluido ({concepto})")
            return False

    # -------------------------
    # Condición por valor
    # -------------------------
    valor = contexto["valor"]
    condicion = regla["condicion_valor"]

    if condicion == "POSITIVO" and valor <= 0:
        print("- Rechazada: valor no positivo")
        return False

    if condicion == "NEGATIVO" and valor >= 0:
        print("- Rechazada: valor no negativo")
        return False

    # -------------------------
    # Requiere origen
    # -------------------------
    if regla.get("requiere_origen") and not contexto.get("origen"):
        print("- Rechazada: origen requerido")
        return False

    print("✓ Regla aplica")
    return True

# ========================
# Motor de operación
# ========================
def aplicar_operacion(accion, contexto):
    valor = contexto["valor"]
    monto = abs(valor)

    if accion["operacion"] == "DECREMENTAR":
        return monto * Decimal(-1)

    if accion["operacion"] in ["INCREMENTAR", "ADD"]:
        return monto

    raise Exception(f"Operación no soportada: {accion['operacion']}")

# ========================
# Handler principal
# ========================
def lambda_handler(event, context):
    print("EVENT RAW:", json.dumps(event))

    records = event if isinstance(event, list) else event.get("Records", [])
    print(f"CHECKPOINT 1 - Records recibidos: {len(records)}")

    reglas = cargar_reglas()

    for record in records:
        try:
            if record.get("eventName") not in ["INSERT", "MODIFY"]:
                print("CHECKPOINT 2 - Evento ignorado")
                continue

            new_image = record.get("dynamodb", {}).get("NewImage")
            if not new_image:
                print("CHECKPOINT 3 - Sin NewImage")
                continue

            item = deserialize(new_image)
            print("CHECKPOINT 4 - ITEM DESERIALIZADO:", item)

            table_name = extract_table_name(record["eventSourceARN"])
            print("CHECKPOINT 5 - TABLE NAME:", table_name)

            context_map = TABLE_CONTEXT_MAP.get(table_name)
            if not context_map:
                print("CHECKPOINT 6 - Tabla no mapeada, se ignora")
                continue

            tipo = context_map["tipo"]
            bloque = context_map["bloque"]

            valor = Decimal(item["valor"])
            dominio = item["dominioFinanciero"]
            corte = item["corte"]

            # Concepto normalizado
            if tipo in ["CUENTA", "TARJETA", "INGRESO"]:
                concepto = item["descripcion"].upper()
            else:
                concepto = item["concepto"].upper()

            # Origen reutilizando campo operativo
            origen = None
            field = context_map.get("origen_field")
            if field and field in item:
                origen = str(item[field]).upper()

            contexto = {
                "tipo": tipo,
                "bloque": bloque,
                "valor": valor,
                "concepto": concepto,
                "dominio": dominio,
                "corte": corte,
                "origen": origen
            }

            print("CHECKPOINT 7 - CONTEXTO NORMALIZADO:", json.dumps(contexto, default=str))

            regla_aplicada = False
            print(f"CHECKPOINT 8 - Evaluando {len(reglas)} reglas")

            for regla in reglas:
                if not regla_aplica(regla, contexto):
                    continue

                regla_aplicada = True

                for accion in regla["acciones"]:
                    monto = aplicar_operacion(accion, contexto)

                    pk = f"{dominio}#{corte}"

                    sk = construir_sk(
                        accion["tipo_destino"],
                        concepto,
                        origen
                    )

                    print(
                        f"CHECKPOINT 9 - APLICANDO REGLA {regla['id']} "
                        f"→ {pk} / {sk} ({monto})"
                    )

                    table.update_item(
                        Key={
                            "Dominio-Corte": pk,
                            "Tipo-Concepto": sk
                        },
                        UpdateExpression="""
                            ADD #v :inc
                            SET tipo = :t,
                                bloque = :b,
                                concepto = :c,
                                origen = :o
                        """,
                        ExpressionAttributeNames={
                            "#v": "valor"
                        },
                        ExpressionAttributeValues={
                            ":inc": monto,
                            ":t": accion["tipo_destino"],
                            ":b": accion["bloque_destino"],
                            ":c": concepto,
                            ":o": origen
                        }
                    )

            # ========================
            # CONSOLIDACIÓN BASE (DEFAULT)
            # ========================
            if not regla_aplicada:
                print("CHECKPOINT DEFAULT - No aplicó regla, consolidación base")

                pk = f"{dominio}#{corte}"

                sk = construir_sk(
                    tipo,
                    concepto,
                    origen
                )

                table.update_item(
                    Key={
                        "Dominio-Corte": pk,
                        "Tipo-Concepto": sk
                    },
                    UpdateExpression="""
                        ADD #v :inc
                        SET tipo = :t,
                            bloque = :b,
                            concepto = :c,
                            origen = :o
                    """,
                    ExpressionAttributeNames={
                        "#v": "valor"
                    },
                    ExpressionAttributeValues={
                        ":inc": valor,
                        ":t": tipo,
                        ":b": bloque,
                        ":c": concepto,
                        ":o": origen if tipo in ["CUENTA", "TARJETA"] else None
                    }
                )

        except Exception as e:
            print("ERROR PROCESANDO RECORD:", str(e))
            print(json.dumps(record))
            raise

    print("CHECKPOINT FINAL - Consolidación terminada")

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Consolidación ejecutada correctamente"})
    }

# ========================
# Utilidades
# ========================
def deserialize(image):
    result = {}
    for k, v in image.items():
        if "S" in v:
            result[k] = v["S"]
        elif "N" in v:
            result[k] = Decimal(v["N"])
    return result

def extract_table_name(arn):
    return arn.split(":table/")[1].split("/")[0]

def construir_sk(tipo, concepto, origen):
    """
    Regla unificada de SK:
    - CUENTA / TARJETA → separan por origen
    - GASTO / INGRESO → NO separan por origen
    """
    if tipo in ["CUENTA", "TARJETA"] and origen:
        return f"{tipo}#{concepto}#{origen}"

    return f"{tipo}#{concepto}"
