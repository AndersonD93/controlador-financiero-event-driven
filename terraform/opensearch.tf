resource "aws_opensearchserverless_collection" "rag" {
  name = "flujo-caja-rag"
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network
  ]
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "rag-encryption"
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/flujo-caja-rag"]
      }
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "network" {
  name = "rag-network"
  type = "network"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/flujo-caja-rag"]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_access_policy" "rag_access" {
  name = "rag-access"
  type = "data"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/flujo-caja-rag/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:WriteDocument",
            "aoss:ReadDocument"
          ]
        }
      ]
      Principal = [
        module.lambdas_backend_api.lambda_role_arns["EmbeddingsToOpenSearch"]
      ]
    }
  ])
}
