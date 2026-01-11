module "s3" {
  source     = "./modules/resources/s3"
  s3_buckets = local.s3_buckets
  project    = var.project
}