output "s3_bucket_website_urls" {
  description = "Website endpoint URLs de los buckets S3 con hosting habilitado"
  value = {
    for k, v in aws_s3_bucket_website_configuration.website :
    k => "http://${v.website_endpoint}"
  }
}

output "bucket_names" {
  description = "Mapa con los nombres de los buckets S3 creados"
  value = {
    for k, b in aws_s3_bucket.this :
    k => b.bucket
  }
}

output "bucket_arns" {
  description = "Mapa con los ARNs de los buckets S3 creados"
  value = {
    for k, b in aws_s3_bucket.this :
    k => b.arn
  }
}
