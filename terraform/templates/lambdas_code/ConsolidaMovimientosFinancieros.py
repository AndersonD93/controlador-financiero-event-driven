import json
import boto3
import os
import time
from decimal import Decimal
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

table = dynamodb.Table(os.getenv("flujo_caja_table"))

REGLAS_PARAM = "/flujo-caja/reglas-compensacion"

# Cache en memoria (cold-start aware)
REGLAS_CACHE = None
REGLAS_CACHE_TS = 0
REGLAS_TTL = 300  # 5 minutos

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


def regla_aplica(regla, contexto):
    print(f"→ Evaluando regla {regla.get('id')}")

    if not regla.get("activo"):
        print("- Rechazada: regla inactiva")
        return False

    if contexto["tipo"] not in regla["tipos_origen"]:
        print("- Rechazada: tipo no coincide")
        return False

    if contexto["bloque"] != regla["bloque_origen"]:
        print("- Rechazada: bloque no coincide")
        return False

    concepto = contexto.get("concepto")
    dominio = contexto.get("dominio")

    if "excluir_conceptos" in regla:
        if concepto in regla["excluir_conceptos"]:
            print(f"- Rechazada: concepto excluido ({concepto})")
            return False

    # Solo aplica si la lista está definida en la regla
    if "incluir_conceptos" in regla:
        if concepto not in regla["incluir_conceptos"]:
            print(f"- Rechazada: concepto no está en incluir_conceptos ({concepto})")
            return False

    # Solo aplica si la lista está definida en la regla
    if "excluir_dominio" in regla:
        if dominio in regla["excluir_dominio"]:
            print(f"- Rechazada: dominio excluido ({dominio})")
            return False

    valor = contexto["valor"]
    condicion = regla["condicion_valor"]

    if condicion == "CUALQUIERA":
        pass
    elif condicion == "POSITIVO" and valor <= 0:
        print("- Rechazada: valor no positivo")
        return False
    elif condicion == "NEGATIVO" and valor >= 0:
        print("- Rechazada: valor no negativo")
        return False

    if regla.get("requiere_origen") and not contexto.get("origen"):
        print("- Rechazada: origen requerido")
        return False

    print("✓ Regla aplica")
    return True


def aplicar_operacion(accion, contexto):
    valor = contexto["valor"]
    monto = abs(valor)

    if accion["operacion"] == "DECREMENTAR":
        return monto * Decimal(-1)

    if accion["operacion"] in ["INCREMENTAR", "ADD"]:
        return monto

    raise Exception(f"Operación no soportada: {accion['operacion']}")


def calcular_monto_seguro(pk, sk, monto_propuesto):
    try:
        response = table.get_item(
            Key={
                "Dominio-Corte": pk,
                "Tipo-Concepto": sk
            },
            ProjectionExpression="#v",
            ExpressionAttributeNames={"#v": "valor"}
        )
        item_actual = response.get("Item")

        if not item_actual:
            print(f"DEBUG MONTO SEGURO → Ítem no existe, decremento bloqueado")
            return Decimal(0)

        valor_actual = item_actual.get("valor", Decimal(0))
        print(f"DEBUG MONTO SEGURO → Actual: {valor_actual} | Propuesto: {monto_propuesto}")

        resultado = valor_actual + monto_propuesto

        if resultado < 0:
            monto_ajustado = monto_propuesto - resultado
            print(f"DEBUG MONTO SEGURO → Ajustado a: {monto_ajustado} (evita negativo)")
            return monto_ajustado

        return monto_propuesto

    except ClientError as e:
        print(f"ERROR MONTO SEGURO: {str(e)}")
        raise


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

            origen = None
            field = context_map.get("origen_field")
            if field and field in item:
                origen = str(item[field]).upper()

            cuenta_destino = item.get("cuentaDestino")
            if cuenta_destino:
                cuenta_destino = str(cuenta_destino).upper()

            contexto = {
                "tipo": tipo,
                "bloque": bloque,
                "valor": valor,
                "concepto": concepto,
                "dominio": dominio,
                "corte": corte,
                "origen": origen,
                "cuenta_destino": cuenta_destino
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

                    # Resolver el origen según la directiva de la acción
                    origen_accion = origen
                    origen_destino = accion.get("origen_destino")

                    if origen_destino == "USAR_CUENTA_DESTINO":
                        origen_accion = contexto.get("cuenta_destino")
                        if not origen_accion:
                            print(f"Acción requiere cuenta_destino pero no está en el contexto, se omite")
                            continue

                    sk = construir_sk(
                        accion["tipo_destino"],
                        concepto,
                        origen_accion
                    )

                    print(f"DEBUG SK GENERADO → PK: {pk} | SK: {sk} | Monto: {monto}")

                    # Protección anti-negativo para PROYECCION
                    if accion["bloque_destino"] == "PROYECCION" and monto < 0:
                        monto = calcular_monto_seguro(pk, sk, monto)

                    if monto == 0:
                        print(f"CHECKPOINT 9b - Monto ajustado a 0, se omite escritura → {sk}")
                        continue

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
                            ":o": origen_accion
                        }
                    )

            # Consolidación base cuando no aplica ninguna regla
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
