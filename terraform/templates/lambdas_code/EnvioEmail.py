import json
import boto3
import os
from datetime import datetime

s3_client  = boto3.client("s3")
ses_client = boto3.client("ses", region_name=os.environ["SES_REGION"])

SES_SENDER         = os.environ["SES_SENDER"]
SES_RECIPIENT      = os.environ["SES_RECIPIENT"]
URL_EXPIRATION_SEC = int(os.environ.get("URL_EXPIRATION_SEC", str(60 * 60 * 24)))  # 24h default


def generate_presigned_url(bucket, key, expiration=URL_EXPIRATION_SEC):
    url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key":    key
        },
        ExpiresIn=expiration
    )
    print(f"URL prefirmada generada — expira en {expiration}s")
    return url


def send_email(destinatario, presigned_url, key, expiration_sec):

    nombre_archivo = key.split("/")[-1]
    expira_horas   = expiration_sec // 3600

    subject = "Reporte Financiero disponible — Controlador Financiero"

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Reporte Financiero generado</h2>
        <p>Tu reporte <strong>{nombre_archivo}</strong> está listo para descargar.</p>

        <p>
            <a href="{presigned_url}"
               style="
                background-color: #0066cc;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 4px;
                display: inline-block;
               ">
                Descargar reporte
            </a>
        </p>

        <p style="color: #888; font-size: 12px;">
            Este enlace expira en <strong>{expira_horas} horas</strong>
            a partir de su generación.<br>
            Si el botón no funciona, copia y pega esta URL en tu navegador:<br>
            <small>{presigned_url}</small>
        </p>

        <hr style="border: none; border-top: 1px solid #eee;">
        <p style="color: #aaa; font-size: 11px;">
            Controlador Financiero — {datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC
        </p>
    </body>
    </html>
    """

    body_text = (
        f"Tu reporte {nombre_archivo} está listo.\n\n"
        f"Descárgalo aquí (válido por {expira_horas} horas):\n{presigned_url}"
    )

    ses_client.send_email(
        Source=SES_SENDER,
        Destination={"ToAddresses": [destinatario]},
        Message={
            "Subject": {"Data": subject,    "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": body_text, "Charset": "UTF-8"},
                "Html": {"Data": body_html, "Charset": "UTF-8"}
            }
        }
    )

    print(f"Email enviado a {destinatario}")


def lambda_handler(event, context):
    try:
        print("EVENTO CRUDO:")
        print(json.dumps(event, indent=2))

        records = event.get("Records", [])

        if not records:
            print("No hay Records en el evento")
            return {"status": "skipped", "reason": "missing records"}

        for record in records:
            bucket = record["s3"]["bucket"]["name"]
            key    = record["s3"]["object"]["key"]

            print(f"Nuevo objeto detectado: s3://{bucket}/{key}")

            presigned_url = generate_presigned_url(bucket, key)
            send_email(SES_RECIPIENT, presigned_url, key, URL_EXPIRATION_SEC)

        return {"status": "ok", "processed": len(records)}

    except Exception as e:
        print(f"Error: {str(e)}")
        raise
