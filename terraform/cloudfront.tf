resource "aws_cloudfront_origin_access_control" "dashboard" {
  name                              = "control-financiero-oac"
  description                       = "OAC para dashboard Controlador Financiero"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "dashboard" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "Controlador Financiero - Dashboard"

  # PriceClass_100 = solo USA + Europa (los más baratos)
  # Para Colombia igual enruta bien y es más económico que All
  price_class = "PriceClass_100"

  origin {
    domain_name              = module.s3.bucket_regional_domain_names["host"]
    origin_id                = "s3-control-financiero-host"
    origin_access_control_id = aws_cloudfront_origin_access_control.dashboard.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-control-financiero-host"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # Cache policy: 1 día para index.html (bajo costo = menos requests a S3)
    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 86400

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  # Manejo de error: si S3 retorna 403/404 sirve index.html
  # Útil si en el futuro agregas rutas SPA
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Certificado default de CloudFront = HTTPS gratis sin ACM
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Project     = "controlador-financiero"
    Environment = "prod"
  }
}


output "dashboard_url" {
  description = "URL del dashboard Controlador Financiero"
  value       = "https://${aws_cloudfront_distribution.dashboard.domain_name}"
}