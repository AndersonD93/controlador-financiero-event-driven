module "s3" {
  source     = "./modules/resources/s3"
  s3_buckets = local.s3_buckets
  project    = var.project
}

resource "aws_s3_bucket_notification" "reporting_triggers" {
  bucket = module.s3.bucket_names["reporting"]

  lambda_function {
    lambda_function_arn = module.lambdas_backend_api.lambda_arns["EmbeddingLambda"]
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "output/rag/"
    filter_suffix       = ".json"
  }

  lambda_function {
    lambda_function_arn = module.lambdas_backend_api.lambda_arns["EnvioEmail"]
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "output/reports/"
    filter_suffix       = ".csv"
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
*/

variable "vector_bucket_name" {
  type    = string
  default = "vector-bucket-rag"
}

resource "aws_s3_bucket_public_access_block" "example" {
  bucket = module.s3.bucket_names["host"]

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "allow_access_from_another_account" {
  bucket = module.s3.bucket_names["host"]
  policy = data.aws_iam_policy_document.allow_access_from_another_principal.json
}

/*
data "aws_iam_policy_document" "allow_access_from_another_principal" {
  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = [
      "s3:GetObject"
    ]

    resources = [
      "${module.s3.bucket_arns["host"]}/*",
    ]
  }
}
*/
data "aws_iam_policy_document" "allow_access_from_another_principal" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions = ["s3:GetObject"]

    resources = ["${module.s3.bucket_arns["host"]}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.dashboard.arn]
    }
  }
}

resource "aws_s3_object" "index_html_file" {
  bucket       = module.s3.bucket_names["host"]
  key          = "index.html"
  source       = "${path.root}/templates/index.html"
  content_type = "text/html"
  etag         = filemd5("${path.root}/templates/index.html")
}
/*
resource "aws_s3_object" "html_files" {
  for_each     = fileset("${path.module}/../../templates/html", "*.html")
  bucket       = aws_s3_bucket.static_site.bucket
  key          = "html/${each.value}"
  source       = "${path.module}/../../templates/html/${each.value}"
  content_type = "text/html"
  etag         = filemd5("${path.module}/../../templates/html/${each.value}")
}

resource "aws_s3_object" "css_files" {
  for_each     = fileset("${path.module}/../../templates/css", "*.css")
  bucket       = aws_s3_bucket.static_site.bucket
  key          = "css/${each.value}"
  source       = "${path.module}/../../templates/css/${each.value}"
  content_type = "text/css"
}

resource "aws_s3_object" "js_files" {
  for_each     = fileset("${path.module}/../../templates/js", "*.js")
  bucket       = aws_s3_bucket.static_site.bucket
  key          = "js/${each.value}"
  source       = "${path.module}/../../templates/js/${each.value}"
  content_type = "application/javascript"
  etag         = filemd5("${path.module}/../../templates/js/${each.value}")
}

*/
