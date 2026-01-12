import json
import boto3
import os
import requests
from requests_aws4auth import AWS4Auth

# ======================
# Configuración
# ======================
REGION = os.environ["AWS_REGION"]
COLLECTION_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
INDEX_NAME = "flujo_caja_vectors"
BEDROCK_MODEL = "amazon.titan-embed-text-v1"

session = boto3.Session()
credentials = session.get_credentials()

awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    REGION,
    "aoss",
    session_token=credentials.token
)

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
s3 = boto3.client("s3")

headers = {"Content-Type": "application/json"}

# ======================
# Crear índice si no existe
# ======================
def ensure_index():
    url = f"{COLLECTION_ENDPOINT}/{INDEX_NAME}"
    payload = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 1536
                },
                "text": {"type": "text"},
                "dominio": {"type": "keyword"},
                "corte": {"type": "keyword"}
            }
        }
    }

    r = requests.put(url, auth=awsauth, headers=headers, json=payload)
    if r.status_code not in [200, 201]:
        print("Index may already exist:", r.text)

# ======================
# Generar embedding
# ======================
def generate_embedding(text):
    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL,
        body=json.dumps({"inputText": text}),
        contentType="application/json",
        accept="application/json"
    )
    body = json.loads(response["body"].read())
    return body["embedding"]

# ======================
# Lambda Handler
# ======================
def lambda_handler(event, context):

    ensure_index()

    bucket = event["bucket"]
    key = event["key"]

    obj = s3.get_object(Bucket=bucket, Key=key)
    lines = obj["Body"].read().decode("utf-8").splitlines()

    for line in lines:
        record = json.loads(line)

        text = (
            f"Dominio {record['dominio']}, "
            f"Corte {record['corte']}, "
            f"Sección {record['seccion']}, "
            f"Concepto {record['concepto']}, "
            f"Valor {record['valor_ajustado']}"
        )

        embedding = generate_embedding(text)

        doc = {
            "text": text,
            "dominio": record["dominio"],
            "corte": record["corte"],
            "embedding": embedding
        }

        url = f"{COLLECTION_ENDPOINT}/{INDEX_NAME}/_doc"
        r = requests.post(url, auth=awsauth, headers=headers, json=doc)

        if r.status_code not in [200, 201]:
            print("Error indexing:", r.text)

    return {"status": "ok"}
