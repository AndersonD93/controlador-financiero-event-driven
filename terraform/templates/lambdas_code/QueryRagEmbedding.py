import json
import boto3
import os

bedrock_runtime = boto3.client("bedrock-runtime")
s3vectors = boto3.client("s3vectors")

VECTOR_BUCKET = os.environ["VECTOR_BUCKET"]
VECTOR_INDEX = os.environ["VECTOR_INDEX"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
LLM_MODEL = os.environ["LLM_MODEL"]
TOP_K = int(os.environ.get("TOP_K", "5"))


# --------------------------------------------------
# 1️⃣ Generar embedding del prompt
# --------------------------------------------------

def get_embedding(text: str):
    response = bedrock_runtime.invoke_model(
        modelId=EMBED_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text
        })
    )

    result = json.loads(response["body"].read())
    return result["embedding"]


# --------------------------------------------------
# 2️⃣ Consultar S3 Vectors
# --------------------------------------------------

def search_similar(embedding):

    response = s3vectors.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        topK=TOP_K,
        queryVector={
            "float32": embedding
        },
        returnMetadata=True
    )

    return response.get("vectors", [])


# --------------------------------------------------
# 3️⃣ Construir contexto
# --------------------------------------------------

def build_context(vectors):

    context_parts = []

    for v in vectors:
        metadata = v.get("metadata", {})
        context_parts.append(
            f"""
Dominio: {metadata.get('dominio')}
Periodo: {metadata.get('corte')}
Sección: {metadata.get('seccion')}
Concepto: {metadata.get('concepto')}
Valor: {metadata.get('valor')}
"""
        )

    return "\n".join(context_parts)


# --------------------------------------------------
# 4️⃣ Invocar LLM (Claude en este ejemplo)
# --------------------------------------------------

def generate_response(question, context):

    prompt = f"""
Eres un asistente financiero.
Responde usando únicamente la información del contexto.

Contexto:
{context}

Pregunta:
{question}
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 800,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    response = bedrock_runtime.invoke_model(
        modelId=LLM_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )

    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


# --------------------------------------------------
# 5️⃣ Handler principal
# --------------------------------------------------

def lambda_handler(event, context):

    # Soporta API Gateway HTTP API
    body = json.loads(event.get("body", "{}"))
    question = body.get("question")

    if not question:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing 'question'"})
        }

    # 1) embedding
    embedding = get_embedding(question)

    # 2) búsqueda vectorial
    vectors = search_similar(embedding)

    if not vectors:
        return {
            "statusCode": 200,
            "body": json.dumps({"answer": "No se encontró información relevante."})
        }

    # 3) contexto
    context_text = build_context(vectors)

    # 4) LLM
    answer = generate_response(question, context_text)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "answer": answer,
            "matches": vectors
        })
    }
