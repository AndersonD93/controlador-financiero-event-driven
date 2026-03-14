import json
import boto3
import hmac
import hashlib
import os

secrets_client = boto3.client("secretsmanager")

signing_secret_cache = None


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


def lambda_handler(event, context):

    headers = event["headers"]
    body = event["body"]

    # Validación de firma
    if not verify_slack_request(headers, body):

        return {
            "statusCode": 401,
            "body": "invalid signature"
        }

    payload = json.loads(body)

    print("Payload recibido de Slack:")
    print(json.dumps(payload, indent=2))

    # Verificación inicial Slack
    if payload.get("type") == "url_verification":

        return {
            "statusCode": 200,
            "body": json.dumps({
                "challenge": payload["challenge"]
            })
        }

    # Solo para pruebas
    if payload.get("type") == "event_callback":

        message = payload["event"].get("text")

        print(f"Mensaje recibido: {message}")

    return {
        "statusCode": 200,
        "body": "ok"
    }