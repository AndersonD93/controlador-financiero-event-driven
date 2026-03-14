module "s3" {
  source     = "./modules/resources/s3"
  s3_buckets = local.s3_buckets
  project    = var.project
}

resource "aws_s3_bucket_notification" "rag_trigger" {
  bucket = module.s3.bucket_names["reporting"]

  lambda_function {
    lambda_function_arn = module.lambdas_backend_api.lambda_arns["EmbeddingLambda"]
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "output/rag/"
    filter_suffix       = ".json"
  }
}

/*
Actualmente el provider no soporta S3 Vectors por tanto se requiere utilzar la CLI version 2 para ejecutar el siguiente comando.

aws s3vectors create-vector-bucket \
  --vector-bucket-name vector-bucket-rag \
  --region us-east-1

aws s3vectors create-index \
  --vector-bucket-name vector-bucket-rag \
  --index-name rag-index \
  --dimension 1536 \
  --data-type float32 \
  --distance-metric cosine \
  --region us-east-1

aws s3vectors create-index \
  --vector-bucket-name vector-bucket-rag \
  --index-name indice-contexto-intenciones \
  --dimension 1536 \
  --data-type float32 \
  --distance-metric cosine \
  --region us-east-1
*/

variable "vector_bucket_name" {
  type    = string
  default = "vector-bucket-rag"
}
