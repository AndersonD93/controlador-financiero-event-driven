import json
import boto3
import hmac
import hashlib
import os
import urllib.parse
import urllib.request
from datetime import datetime

# AWS clients
secrets_client = boto3.client("secretsmanager")
lambda_client = boto3.client("lambda")

# Cache secreto
signing_secret_cache = None

SLACK_TOKEN_NAME = os.environ["SLACK_BOT_TOKEN"]


def get_signing_secret():
    global signing_secret_cache

    if signing_secret_cache:
        return signing_secret_cache

    secret_name = os.environ["SLACK_SECRET_NAME"]

    response = secrets_client.get_secret_value(
        SecretId=secret_name
    )

    secret = json.loads(response["SecretString"])
    signing_secret_cache = secret["signing_secret"]

    return signing_secret_cache


def verify_slack_request(headers, body):
    signing_secret = get_signing_secret()

    slack_signature = headers.get("X-Slack-Signature")
    timestamp = headers.get("X-Slack-Request-Timestamp")

    base_string = f"v0:{timestamp}:{body}"

    my_signature = "v0=" + hmac.new(
        signing_secret.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, slack_signature)


from catalogo_financiero import (
    cargar_catalogo,
    obtener_conceptos_validos,
    obtener_cuentas_validas
)

TIPO_REGISTRO_MOVIMIENTO = "MOVIMIENTO_GENERAL"
TIPO_REGISTRO_TARJETA = "MOVIMIENTO_TARJETA"
TIPO_REGISTRO_PROYECCION = "PROYECCION"

def build_options(items):
    return [
        {
            "text": {"type": "plain_text", "text": item},
            "value": item
        }
        for item in items
    ]

def find_option(options, value):
    for opt in options:
        if opt["value"] == value:
            return opt
    return None

def generar_cortes(n=6):
    hoy = datetime.utcnow()
    year = hoy.year
    month = hoy.month

    cortes = []
    for i in range(n):
        m = month + i
        y = year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        cortes.append(f"{y}-{m:02d}")

    return cortes


def build_modal(catalogo, dominio=None, state=None):

    dominios = list(catalogo.keys())

    tipo_registro = (state.get("tipo_registro") if state else None) or TIPO_REGISTRO_MOVIMIENTO

    dominio_actual = dominio or (state.get("dominio") if state else None) or dominios[0]

    bloques_disponibles = catalogo.get(dominio_actual, {}).keys()

    incluir_cuenta = True
    incluir_concepto = True

    if tipo_registro == TIPO_REGISTRO_PROYECCION:
        incluir_cuenta = False

    conceptos = []
    cuentas = []

    if incluir_concepto and "PROYECCION" in bloques_disponibles:
        conceptos = obtener_conceptos_validos(
            catalogo,
            dominio_actual,
            "PROYECCION"
        )

    if incluir_cuenta and "CAJA_ACTUAL" in bloques_disponibles:
        cuentas = obtener_cuentas_validas(
            catalogo,
            dominio_actual,
            "CAJA_ACTUAL"
        )

    tipo_options = [
        {
            "text": {"type": "plain_text", "text": "Registrar movimiento de cuenta/inversión/ahorro"},
            "value": TIPO_REGISTRO_MOVIMIENTO
        },
        {
            "text": {"type": "plain_text", "text": "Registrar movimiento de tarjeta"},
            "value": TIPO_REGISTRO_TARJETA
        },
        {
            "text": {"type": "plain_text", "text": "Registrar proyección de gasto/ingreso"},
            "value": TIPO_REGISTRO_PROYECCION
        }
    ]

    tipo_element = {
        "type": "static_select",
        "action_id": "tipo_registro_select",
        "options": tipo_options
    }

    tipo_initial = find_option(tipo_options, tipo_registro)
    if tipo_initial:
        tipo_element["initial_option"] = tipo_initial

    dominio_options = build_options(dominios)
    dominio_initial = find_option(dominio_options, dominio_actual)

    dominio_element = {
        "type": "static_select",
        "action_id": "dominio_select",
        "options": dominio_options
    }

    if dominio_initial:
        dominio_element["initial_option"] = dominio_initial

    cuenta_element = None
    if cuentas:
        cuenta_options = build_options(cuentas)
        cuenta_value = state.get("cuenta") if state else None
        cuenta_initial = find_option(cuenta_options, cuenta_value)

        cuenta_element = {
            "type": "static_select",
            "action_id": "cuenta_select",
            "options": cuenta_options
        }

        if cuenta_initial:
            cuenta_element["initial_option"] = cuenta_initial

    concepto_element = None
    if conceptos:
        concepto_options = build_options(conceptos)
        concepto_value = state.get("concepto") if state else None
        concepto_initial = find_option(concepto_options, concepto_value)

        concepto_element = {
            "type": "static_select",
            "action_id": "concepto_select",
            "options": concepto_options
        }

        if concepto_initial:
            concepto_element["initial_option"] = concepto_initial

    cortes = generar_cortes()
    corte_options = build_options(cortes)
    corte_value = state.get("corte") if state else cortes[0]
    corte_initial = find_option(corte_options, corte_value)

    corte_element = {
        "type": "static_select",
        "action_id": "corte_select",
        "options": corte_options
    }

    if corte_initial:
        corte_element["initial_option"] = corte_initial

    blocks = []

    blocks.append({
        "type": "input",
        "block_id": "tipo_registro",
        "dispatch_action": True,
        "label": {"type": "plain_text", "text": "Tipo de registro"},
        "element": tipo_element
    })

    blocks.append({
        "type": "input",
        "block_id": "dominio",
        "dispatch_action": True,
        "label": {"type": "plain_text", "text": "Dominio"},
        "element": dominio_element
    })

    blocks.append({
        "type": "input",
        "block_id": "corte",
        "label": {"type": "plain_text", "text": "Corte"},
        "element": corte_element
    })

    if cuenta_element and incluir_cuenta:
        blocks.append({
            "type": "input",
            "block_id": "cuenta",
            "label": {"type": "plain_text", "text": "Cuenta"},
            "element": cuenta_element
        })

    if concepto_element and incluir_concepto:
        blocks.append({
            "type": "input",
            "block_id": "concepto",
            "label": {"type": "plain_text", "text": "Concepto"},
            "element": concepto_element
        })

    blocks.append({
        "type": "input",
        "block_id": "descripcion",
        "optional": True,
        "label": {"type": "plain_text", "text": "Descripción"},
        "element": {
            "type": "plain_text_input",
            "action_id": "descripcion_input",
            "initial_value": (state.get("descripcion") or "") if state else ""
        }
    })

    blocks.append({
        "type": "input",
        "block_id": "valor",
        "label": {"type": "plain_text", "text": "Valor"},
        "element": {
            "type": "plain_text_input",
            "action_id": "valor_input",
            "initial_value": (state.get("valor") or "") if state else ""
        }
    })

    return {
        "type": "modal",
        "callback_id": "registro_financiero",
        "private_metadata": json.dumps({
            "channel_id": (state or {}).get("channel_id")
        }),
        "title": {"type": "plain_text", "text": "Control Financiero"},
        "submit": {"type": "plain_text", "text": "Guardar"},
        "blocks": blocks
    }


def get_slack_token():
    response = secrets_client.get_secret_value(
        SecretId=SLACK_TOKEN_NAME
    )

    secret = json.loads(response["SecretString"])

    return secret["SLACK_BOT_TOKEN"]


def open_modal(trigger_id, modal):

    url = "https://slack.com/api/views.open"

    slack_token = get_slack_token()

    payload = json.dumps({
        "trigger_id": trigger_id,
        "view": modal
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {slack_token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req) as response:
        response_body = response.read().decode()
        print("Slack response:", response_body)


ROUTER_FUNCTION_ARN = os.environ["ROUTER_FUNCTION_ARN"]
QUERY_FUNCTION_ARN = os.environ["QUERY_FUNCTION_ARN"]

def invoke_router(payload):

    lambda_client.invoke(
        FunctionName=ROUTER_FUNCTION_ARN,
        InvocationType="Event",
        Payload=json.dumps(payload)
    )

def invoke_query_lambda(payload):

    lambda_client.invoke(
        FunctionName=QUERY_FUNCTION_ARN,
        InvocationType="Event",
        Payload=json.dumps(payload)
    )


def parse_body(body):

    # Slack slash commands vienen urlencoded
    if body.startswith("payload="):
        decoded = urllib.parse.parse_qs(body)
        return json.loads(decoded["payload"][0])

    # slash command normal
    if "trigger_id" in body:
        return urllib.parse.parse_qs(body)

    return json.loads(body)

def update_modal(view_id, modal):

    url = "https://slack.com/api/views.update"

    slack_token = get_slack_token()

    payload = json.dumps({
        "view_id": view_id,
        "view": modal
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {slack_token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req) as response:
        print("Respuesta Slack:", response.read().decode())
 
      
def extract_state(values):

    def get_value(block, action):
        try:
            item = values.get(block, {}).get(action, {})

            selected = item.get("selected_option")
            if selected and isinstance(selected, dict):
                return selected.get("value")

            if "value" in item and item["value"] is not None:
                return item["value"]

            return None

        except Exception as e:
            print(f"Error leyendo {block}.{action}: {str(e)}")
            return None

    return {
        "tipo_registro": get_value("tipo_registro", "tipo_registro_select"),
        "dominio": get_value("dominio", "dominio_select"),
        "corte": get_value("corte", "corte_select"),
        "cuenta": get_value("cuenta", "cuenta_select"),
        "concepto": get_value("concepto", "concepto_select"),
        "descripcion": get_value("descripcion", "descripcion_input"),
        "valor": get_value("valor", "valor_input")
    }
    
def build_modal_consulta(metadata=None):

    return {
        "type": "modal",
        "callback_id": "consulta_financiera",
        "private_metadata": json.dumps(metadata or {}),
        "title": {
            "type": "plain_text",
            "text": "Consulta Financiera"
        },
        "submit": {
            "type": "plain_text",
            "text": "Consultar"
        },
        "close": {
            "type": "plain_text",
            "text": "Cancelar"
        },
        "blocks": [
            {
                "type": "input",
                "block_id": "question",
                "label": {
                    "type": "plain_text",
                    "text": "¿Qué deseas consultar?"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "question_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Ej: ¿Cuánto tengo en inversiones?"
                    }
                }
            }
        ]
    }           


RULES = {
    TIPO_REGISTRO_PROYECCION: {
        "requiere_cuenta": False,
        "requiere_concepto": True,
        "bloque_concepto": "PROYECCION",
        "bloque_cuenta": None
    },
    TIPO_REGISTRO_MOVIMIENTO: {
        "requiere_cuenta": True,
        "requiere_concepto": True,
        "bloque_concepto": "PROYECCION",
        "bloque_cuenta": "CAJA_ACTUAL"
    },
    TIPO_REGISTRO_TARJETA: {
        "requiere_cuenta": True,
        "requiere_concepto": True,
        "bloque_concepto": "PROYECCION",
        "bloque_cuenta": "CAJA_ACTUAL"
    }
}


def validate_submission(state, catalogo):

    errores = {}

    tipo = state.get("tipo_registro")
    dominio = state.get("dominio")
    cuenta = state.get("cuenta")
    concepto = state.get("concepto")

    if not tipo:
        errores["tipo_registro"] = "Debes seleccionar el tipo de registro"

    if not dominio:
        errores["dominio"] = "Debes seleccionar un dominio"
        return errores

    reglas = RULES.get(tipo)

    if not reglas:
        errores["tipo_registro"] = "Tipo de registro inválido"
        return errores

    if reglas["requiere_cuenta"]:

        if not cuenta:
            errores["cuenta"] = "La cuenta es obligatoria"
        else:
            cuentas_validas = obtener_cuentas_validas(
                catalogo,
                dominio,
                reglas["bloque_cuenta"]
            )

            if cuenta not in cuentas_validas:
                errores["cuenta"] = "Cuenta no válida para este dominio"

    else:
        if cuenta:
            errores["cuenta"] = "Este tipo de registro no permite cuenta"

    bloques = catalogo.get(dominio, {})
    tiene_proyeccion = "PROYECCION" in bloques

    if reglas["requiere_concepto"] and tiene_proyeccion:

        if not concepto:
            errores["concepto"] = "El concepto es obligatorio"
        else:
            conceptos_validos = obtener_conceptos_validos(
                catalogo,
                dominio,
                reglas["bloque_concepto"]
            )

            if concepto not in conceptos_validos:
                errores["concepto"] = "Concepto no válido para este dominio"
                
    return errores
    

def lambda_handler(event, context):

    print("==== RAW EVENT ====")
    print(json.dumps(event, indent=2))

    headers = event.get("headers", {})
    raw_body = event.get("body", "")

    print("==== RAW BODY ====")
    print(raw_body)

    if not verify_slack_request(headers, raw_body):
        print("Firma inválida")
        return {
            "statusCode": 401,
            "body": "invalid signature"
        }

    body = parse_body(raw_body)

    print("==== PARSED BODY ====")
    print(json.dumps(body, indent=2))

    # SLASH COMMANDS
    if isinstance(body, dict) and "command" in body:

        print("Detectado SLASH COMMAND")

        raw_command = body["command"]

        command = raw_command[0] if isinstance(raw_command, list) else raw_command

        print("Command normalizado:", command)

        trigger_id = body["trigger_id"][0] if isinstance(body["trigger_id"], list) else body["trigger_id"]

        if command == "/registrar":

            print("Abrir modal REGISTRO")

            channel_id = body.get("channel_id")
            if isinstance(channel_id, list):
                channel_id = channel_id[0]

            print("channel_id capturado:", channel_id)

            catalogo = cargar_catalogo()
            modal = build_modal(catalogo, state={"channel_id": channel_id})

            open_modal(trigger_id, modal)

        elif command == "/consulta":

            print("Abrir modal CONSULTA")

            channel_id = body.get("channel_id")
            if isinstance(channel_id, list):
                channel_id = channel_id[0]

            metadata = {
                "channel_id": channel_id
            }

            modal = build_modal_consulta(metadata)

            open_modal(trigger_id, modal)

        else:
            print(f"Comando no soportado: {command}")

        return {
            "statusCode": 200,
            "body": ""
        }

    # BLOCK ACTIONS
    if isinstance(body, dict) and body.get("type") == "block_actions":

        action = body["actions"][0]
        catalogo = cargar_catalogo()
        state = extract_state(body["view"]["state"]["values"])

        channel_id = None
        metadata_raw = body.get("view", {}).get("private_metadata")

        if metadata_raw:
            try:
                modal_metadata = json.loads(metadata_raw)
                channel_id = modal_metadata.get("channel_id")
            except Exception as e:
                print("Error parsing private_metadata:", str(e))

        if channel_id:
            state["channel_id"] = channel_id

        if action["action_id"] == "tipo_registro_select":
            state["tipo_registro"] = action["selected_option"]["value"]
            state["cuenta"] = None
            state["concepto"] = None

        if action["action_id"] == "dominio_select":
            state["dominio"] = action["selected_option"]["value"]
            state["cuenta"] = None
            state["concepto"] = None

        new_modal = build_modal(catalogo, state=state)
        update_modal(body["view"]["id"], new_modal)

        return {"statusCode": 200, "body": ""}

    # VIEW SUBMISSION
    elif isinstance(body, dict) and body.get("type") == "view_submission":

        print("Detectado VIEW SUBMISSION")

        callback_id = body["view"]["callback_id"]
        values = body["view"]["state"]["values"]

        if callback_id == "registro_financiero":

            print("Validando registro")

            catalogo = cargar_catalogo()

            state = extract_state(values)

            print("State extraído:", json.dumps(state, indent=2))

            errores = validate_submission(state, catalogo)

            if errores:
                print("Errores de validación:", errores)

                return {
                    "statusCode": 200,
                    "body": json.dumps({
                        "response_action": "errors",
                        "errors": errores
                    })
                }

            print("Validación exitosa")

            channel_id = None
            metadata_raw = body.get("view", {}).get("private_metadata")

            if metadata_raw:
                try:
                    modal_metadata = json.loads(metadata_raw)
                    channel_id = modal_metadata.get("channel_id")
                except Exception as e:
                    print("Error parsing private_metadata:", str(e))

            print("channel_id:", channel_id)

            invoke_router({
                "state": state,
                "raw": body,
                "channel_id": channel_id
            })

        elif callback_id == "consulta_financiera":

            print("Procesando consulta")

            try:
                question = values["question"]["question_input"]["value"]
            except Exception:
                question = ""

            print("Pregunta:", question)

            metadata_raw = body.get("view", {}).get("private_metadata")

            channel_id = None

            if metadata_raw:
                try:
                    metadata = json.loads(metadata_raw)
                    channel_id = metadata.get("channel_id")
                except Exception as e:
                    print("Error parsing metadata:", str(e))

            print("channel_id:", channel_id)

            invoke_query_lambda({
                "question": question,
                "channel_id": channel_id,
                "user_id": body["user"]["id"]
            })

            print("response_urls raw:", body.get("response_urls"))

        return {
            "statusCode": 200,
            "body": json.dumps({"response_action": "clear"})
        }

    else:
        print("Evento no reconocido")
        return {
            "statusCode": 200,
            "body": "ok"
        }
