resource "aws_s3_bucket" "this" {
  for_each = var.s3_buckets

  bucket = each.value.name
  tags = {
    Project = var.project
    Name    = each.key
  }
}

resource "aws_s3_bucket_website_configuration" "website" {
  for_each = {
    for k, v in var.s3_buckets : k => v if v.website
  }

  bucket = aws_s3_bucket.this[each.key].bucket

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = var.s3_buckets

  bucket = aws_s3_bucket.this[each.key].bucket

  block_public_acls       = !each.value.public_access
  block_public_policy     = !each.value.public_access
  ignore_public_acls      = !each.value.public_access
  restrict_public_buckets = !each.value.public_access
}

resource "aws_s3_bucket_policy" "public_read" {
  for_each = {
    for k, v in var.s3_buckets : k => v if v.public_access
  }

  bucket = aws_s3_bucket.this[each.key].bucket
  policy = data.aws_iam_policy_document.public_read[each.key].json
}

data "aws_iam_policy_document" "public_read" {
  for_each = {
    for k, v in var.s3_buckets : k => v if v.public_access
  }

  statement {
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = ["s3:GetObject"]

    resources = [
      "${aws_s3_bucket.this[each.key].arn}/*"
    ]
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = {
    for k, v in var.s3_buckets :
    k => v if v.lifecycle_days != null
  }

  bucket = aws_s3_bucket.this[each.key].bucket

  rule {
    id     = "expire-objects"
    status = "Enabled"

    expiration {
      days = each.value.lifecycle_days
    }
  }
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

resource "aws_s3_object" "index_html_file" {
  bucket       = aws_s3_bucket.static_site.bucket
  key          = "index.html"
  source       = "${path.module}/../../templates/index.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/../../templates/index.html")
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

resource "aws_s3_object" "index_html" {
  bucket       = aws_s3_bucket.static_site.bucket
  key          = "index.html"
  source       = "${path.module}/../../templates/index.html"
  content_type = "text/html"
}

*/