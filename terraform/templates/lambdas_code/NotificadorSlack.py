import json
import boto3
import os
import urllib.request

# =========================
# AWS clients
# =========================
secrets_client = boto3.client("secretsmanager")

# =========================
# Config
# =========================
SLACK_TOKEN_NAME = os.environ["SLACK_BOT_TOKEN"]

# =========================
# Emojis por detail-type
# =========================
EMOJIS = {
    "movimiento.tarjeta.registrado": "💳",
    "movimiento.cuenta.registrado":  "🏦",
    "concepto.fijo.registrado":      "📌",
}

# =========================
# 🔐 Token Slack — cache en memoria
# =========================
slack_token_cache = None

def get_slack_token():
    global slack_token_cache

    if slack_token_cache:
        return slack_token_cache

    response = secrets_client.get_secret_value(
        SecretId=SLACK_TOKEN_NAME
    )

    secret = json.loads(response["SecretString"])
    slack_token_cache = secret["SLACK_BOT_TOKEN"]

    return slack_token_cache


# =========================
# 📤 chat.postMessage
# =========================
def post_message(channel_id, blocks):

    url = "https://slack.com/api/chat.postMessage"

    token = get_slack_token()

    payload = json.dumps({
        "channel": channel_id,
        "blocks": blocks,
        "text": "Nuevo registro — Controlador Financiero"
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req) as response:
        body = response.read().decode("utf-8")
        print(f"✅ Slack response: {body}")
        return json.loads(body)


# =========================
# 🧱 Builder mensaje
# =========================
def build_blocks(detail_type, detail):

    emoji    = EMOJIS.get(detail_type, "📬")
    trx_id   = detail.get("trx_id", "N/A")
    dominio  = detail.get("dominioFinanciero", "N/A")
    concepto = detail.get("concepto") or detail.get("descripcion", "N/A")
    valor    = detail.get("valor", "N/A")
    corte    = detail.get("corte", "N/A")
    user_id  = detail.get("user_id", "N/A")
    source   = detail.get("source", "N/A")

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Nuevo registro — Controlador Financiero"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Tipo:*\n{detail_type}"},
                {"type": "mrkdwn", "text": f"*Dominio:*\n{dominio}"},
                {"type": "mrkdwn", "text": f"*Concepto:*\n{concepto}"},
                {"type": "mrkdwn", "text": f"*Valor:*\n${valor}"},
                {"type": "mrkdwn", "text": f"*Corte:*\n{corte}"},
                {"type": "mrkdwn", "text": f"*Usuario:*\n{user_id}"},
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🔎 Source: `{source}` | 🆔 `{trx_id}`"
                }
            ]
        },
        {"type": "divider"}
    ]


# =========================
# 🚀 Handler
# =========================
def lambda_handler(event, context):
    try:
        print("🔥 EVENTO CRUDO:")
        print(json.dumps(event, indent=2))

        detail_type = event.get("detail-type", "unknown")
        detail      = event.get("detail", {})

        if isinstance(detail, str):
            detail = json.loads(detail)

        print(f"📨 detail-type: {detail_type}")
        print(f"📦 detail: {json.dumps(detail, indent=2)}")

        # =========================
        # 📍 channel_id desde detail
        # =========================
        channel_id = detail.get("channel_id")

        if not channel_id:
            print("❌ channel_id no presente en el detail, no se puede notificar")
            return {"status": "skipped", "reason": "missing channel_id"}

        # =========================
        # 🧱 Construir y enviar
        # =========================
        blocks = build_blocks(detail_type, detail)

        result = post_message(channel_id, blocks)

        if not result.get("ok"):
            print(f"⚠️ Slack error: {result.get('error')}")
            raise Exception(f"Slack API error: {result.get('error')}")

        print(f"📨 Mensaje enviado al canal {channel_id} — ts: {result.get('ts')}")

        return {"status": "ok", "ts": result.get("ts")}

    except Exception as e:
        print(f"❌ Error al notificar Slack: {str(e)}")
        raise