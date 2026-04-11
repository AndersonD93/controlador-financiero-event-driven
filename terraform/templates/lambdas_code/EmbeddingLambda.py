import json
import boto3
import os
import urllib.parse

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")
s3vectors = boto3.client("s3vectors")

VECTOR_BUCKET = os.environ["VECTOR_BUCKET"]
VECTOR_INDEX = os.environ["VECTOR_INDEX"]
EMBED_MODEL = os.environ["EMBED_MODEL"]


def reset_index():
    try:
        print("Eliminando índice existente...")
        s3vectors.delete_index(
            vectorBucketName=VECTOR_BUCKET,
            indexName=VECTOR_INDEX
        )
    except Exception as e:
        print("Índice no existía:", str(e))

    print("Creando índice nuevo...")

    s3vectors.create_index(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        dataType="float32",
        dimension=1536,
        distanceMetric="cosine"
    )


def get_embedding(text):
    response = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({
            "inputText": text
        }),
        contentType="application/json",
        accept="application/json"
    )

    result = json.loads(response["body"].read())
    return result["embedding"]


def resolve_source(event):
    """
    Soporta:
    1) Evento S3 automático
    2) Ejecución manual desde consola AWS
    """

    # Caso 1 — Evento S3
    if "Records" in event:
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(
            event["Records"][0]["s3"]["object"]["key"]
        )
        return bucket, key

    # Caso 2 — Invocación manual
    if "bucket" in event and "key" in event:
        return event["bucket"], event["key"]

    raise ValueError("Evento inválido. Debe contener Records (S3) o bucket/key manual.")


def lambda_handler(event, context):
    
    reset_index()

    print("Evento recibido:", json.dumps(event))

    bucket, key = resolve_source(event)

    print(f"Leyendo archivo desde: s3://{bucket}/{key}")

    obj = s3.get_object(Bucket=bucket, Key=key)
    lines = obj["Body"].read().decode("utf-8").splitlines()

    vectors_to_insert = []

    for line in lines:
        if not line.strip():
            continue

        doc = json.loads(line)

        embedding = get_embedding(doc["texto"])

        vectors_to_insert.append({
            "key": doc["id"],
            "data": {
                "float32": embedding
            },
            "metadata": {
                "dominio": doc.get("dominio"),
                "corte": doc.get("corte"),
                "categoria_bloque": doc.get("categoria_bloque"),
                "tipo_registro": doc.get("tipo_registro"),
                "es_futuro": doc.get("es_futuro"),
                "seccion": doc.get("seccion"),
                "concepto": doc.get("concepto"),
                "valor": doc.get("valor")
            }
        })

        # Insertar en lotes de 50
        if len(vectors_to_insert) == 50:
            s3vectors.put_vectors(
                vectorBucketName=VECTOR_BUCKET,
                indexName=VECTOR_INDEX,
                vectors=vectors_to_insert
            )
            vectors_to_insert = []

    # Insertar resto
    if vectors_to_insert:
        s3vectors.put_vectors(
            vectorBucketName=VECTOR_BUCKET,
            indexName=VECTOR_INDEX,
            vectors=vectors_to_insert
        )

    return {
        "status": "ok",
        "source_bucket": bucket,
        "source_key": key
    }