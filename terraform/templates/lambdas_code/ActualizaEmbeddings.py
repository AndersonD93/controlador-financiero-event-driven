import boto3
import json
import os

ssm = boto3.client("ssm")
bedrock = boto3.client("bedrock-runtime")
s3vectors = boto3.client("s3vectors")

PARAMETER_NAME = os.environ.get("PARAMETER_NAME", "/ai-router/intents")
VECTOR_BUCKET = os.environ["VECTOR_BUCKET"]
VECTOR_INDEX = os.environ["VECTOR_INDEX"]
EMBED_MODEL = os.environ["EMBED_MODEL"]


def get_router_config():

    response = ssm.get_parameter(
        Name=PARAMETER_NAME
    )

    return json.loads(response["Parameter"]["Value"])


def generate_embedding(text):

    body = json.dumps({
        "inputText": text
    })

    response = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=body
    )

    result = json.loads(response["body"].read())

    return result["embedding"]


def build_context(intent):

    text = intent["description"] + "\n"

    if "keywords" in intent:
        text += "keywords: " + ", ".join(intent["keywords"]) + "\n"

    text += "examples:\n"

    for example in intent["examples"]:
        text += "- " + example + "\n"

    return text


def upsert_vector(intent):

    context_text = build_context(intent)

    embedding = generate_embedding(context_text)

    try:
        s3vectors.delete_vector(
            vectorBucketName=VECTOR_BUCKET,
            indexName=VECTOR_INDEX,
            id=intent["intent"]
        )
    except Exception:
        pass

    s3vectors.put_vector(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        id=intent["intent"],
        vector=embedding,
        metadata={
            "intent": intent["intent"],
            "lambda": intent["lambda"],
            "payload_schema": json.dumps(intent["payload"])
        }
    )


def lambda_handler(event, context):

    config = get_router_config()

    for fn in config["functions"]:
        upsert_vector(fn)

    return {
        "statusCode": 200,
        "message": "Embeddings actualizados correctamente"
    }