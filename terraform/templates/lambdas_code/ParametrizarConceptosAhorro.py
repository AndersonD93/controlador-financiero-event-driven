import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

from catalogo_financiero import (
    cargar_catalogo,
    validar_dominio,
    obtener_conceptos_validos,
    normalizar_evento
)

# =========================
# AWS clients
# =========================
dynamodb = boto3.resource("dynamodb")

# =========================
# DynamoDB tables
# =========================
table_casa = dynamodb.Table(os.getenv("conceptos_fijos_table"))
table_personal = dynamodb.Table(os.getenv("conceptos_fijos_persona_table"))

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
# 🧩 Helper respuesta
# =========================
def build_response(source, status, body):
    if source == "apigateway":
        return {
            "statusCode": status,
            "headers": HEADERS,
            "body": json.dumps(body)
        }
    return body

def publicar_evento(detail_type, item, source, channel_id=None):
    try:
        eventbridge = boto3.client("events")

        eventbridge.put_events(Entries=[{
            "Source": "app.financiero",
            "DetailType": detail_type,
            "Detail": json.dumps({
                "trx_id":            item["trx_id"],
                "dominioFinanciero": item.get("dominioFinanciero"),
                "concepto":          item.get("concepto") or item.get("descripcion"),
                "descripcion":       item.get("descripcion"),
                "valor":             str(item.get("valor")),
                "corte":             item.get("corte"),
                "user_id":           item.get("user_id"),
                "source":            source,
                "channel_id":        channel_id
            }),
            "EventBusName": os.getenv("EVENT_BUS_NAME")
        }])

        print(f"📡 Evento publicado: {detail_type}")

    except Exception as e:
        print(f"⚠️ Error publicando evento en EventBridge: {str(e)}")

# =========================
# 🚀 Handler
# =========================
def lambda_handler(event, context):
    try:
        print("🔥 EVENTO CRUDO:")
        print(json.dumps(event, indent=2))

        # =========================
        # 🧠 Normalización única
        # =========================
        payload, metadata, source = normalizar_evento(event)

        if not isinstance(payload, dict):
            print("⚠️ Payload inválido, se fuerza a {}")
            payload = {}

        metadata = metadata or {}

        print("📦 Payload normalizado:")
        print(json.dumps(payload, indent=2))

        print("🧾 Metadata:")
        print(json.dumps(metadata, indent=2))

        print("🔎 Source:", source)

        # =========================
        # ✅ Validación obligatoria
        # =========================
        required_fields = [
            "DominioFinanciero",
            "Concepto",
            "Valor",
            "Corte"
        ]

        missing = [f for f in required_fields if not payload.get(f)]

        if missing:
            error = {
                "message": "Campos obligatorios faltantes",
                "missing_fields": missing
            }
            print("❌", error)
            return build_response(source, 400, error)

        # =========================
        # 🧠 Normalización de valores
        # =========================
        dominio = payload["DominioFinanciero"].strip().upper()
        concepto = payload["Concepto"].strip().upper()
        subconcepto = payload.get("Subconcepto")

        if subconcepto:
            subconcepto = subconcepto.strip().upper()

        # 🔥 Normalizar valor numérico
        try:
            valor = Decimal(str(payload["Valor"]))
        except Exception:
            return build_response(source, 400, {
                "message": "Valor debe ser numérico",
                "valor_recibido": payload["Valor"]
            })

        # =========================
        # 📦 Cargar catálogo
        # =========================
        catalogo = cargar_catalogo()

        # =========================
        # ✅ Validar dominio
        # =========================
        try:
            validar_dominio(catalogo, dominio)
        except ValueError as e:
            return build_response(source, 400, {"message": str(e)})

        # =========================
        # ✅ Selección de tabla
        # =========================
        if dominio == "CASA":
            table = table_casa
        elif dominio in ["PERSONAL", "AHORRO", "INVERSIONES"]:
            table = table_personal
        else:
            return build_response(source, 400, {
                "message": "DominioFinanciero inválido"
            })

        # =========================
        # ✅ Validar concepto
        # =========================
        try:
            conceptos_validos = obtener_conceptos_validos(
                catalogo,
                dominio,
                "PROYECCION"
            )
        except ValueError as e:
            return build_response(source, 500, {
                "message": str(e),
                "dominio": dominio
            })

        if concepto not in conceptos_validos:
            return build_response(source, 400, {
                "message": "Concepto no permitido según el catálogo",
                "concepto": concepto,
                "dominio": dominio,
                "permitidos": conceptos_validos
            })

        # =========================
        # 🧱 Construcción item
        # =========================
        item = {
            "trx_id": str(uuid.uuid4()),
            "dominioFinanciero": dominio,
            "concepto": concepto,
            "valor": valor,
            "corte": payload["Corte"],
            "created_at": datetime.utcnow().isoformat(),
            "origen_registro": "PROYECCION_MANUAL",
            "user_id": metadata.get("user_id")
        }

        if subconcepto:
            item["subconcepto"] = subconcepto

        print("📝 Item a guardar:")
        print(json.dumps(item, indent=2, default=str))

        # =========================
        # 💾 Persistencia
        # =========================
        table.put_item(Item=item)
        if source == "eventbridge":
            publicar_evento("concepto.fijo.confirmado", item, source,channel_id=metadata.get("channel_id"))
        # =========================
        # 📤 Respuesta
        # =========================
        response = {
            "message": "Concepto registrado correctamente",
            "trx_id": item["trx_id"],
            "tabla_destino": table.name
        }

        return build_response(source, 200, response)

    except Exception as e:
        print("❌ Error:", str(e))
        return {
            "statusCode": 500,
            "headers": HEADERS,
            "body": json.dumps({
                "message": "Error interno al registrar concepto",
                "error": str(e)
            })
        }