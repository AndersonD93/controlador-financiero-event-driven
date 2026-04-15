locals {
  catalogo_financiero_value   = file("${path.module}/../../../templates/reglas/catalogo_financiero.json")
  reglas_compensacion_value   = file("${path.module}/../../../templates/reglas/reglas_compensacion.json")
  proyecciones_fijas_value    = file("${path.module}/../../../templates/reglas/proyecciones_fijas.json")

  catalogo_financiero_hash    = filesha256("${path.module}/../../../templates/reglas/catalogo_financiero.json")
  reglas_compensacion_hash    = filesha256("${path.module}/../../../templates/reglas/reglas_compensacion.json")
  proyecciones_fijas_hash     = filesha256("${path.module}/../../../templates/reglas/proyecciones_fijas.json")
}



resource "aws_ssm_parameter" "catalogo_financiero" {
  name        = "/${var.prefix}/catalogo_financiero"
  description = "Catálogo de conceptos válidos para flujo de caja"
  type        = "String"
  tier        = "Standard"
  value       = local.catalogo_financiero_value
  overwrite   = true

  tags = {
    proyecto     = "flujo-caja"
    tipo         = "catalogo_financiero"
    content_hash = local.catalogo_financiero_hash
  }
}


resource "aws_ssm_parameter" "reglas_compensacion" {
  name        = "/${var.prefix}/reglas-compensacion"
  description = "Reglas de compensación para flujo de caja"
  type        = "String"
  tier        = "Advanced"
  value       = local.reglas_compensacion_value
  overwrite   = true

  tags = {
    proyecto     = "flujo-caja"
    tipo         = "reglas-compensacion"
    content_hash = local.reglas_compensacion_hash
  }
}


resource "aws_ssm_parameter" "proyecciones_fijas" {
  name        = "/${var.prefix}/proyecciones-fijas"
  description = "Reglas de proyecciones fijas"
  type        = "String"
  tier        = "Standard"
  value       = local.proyecciones_fijas_value
  overwrite   = true

  tags = {
    proyecto     = "flujo-caja"
    tipo         = "reglas-compensacion"
    content_hash = local.proyecciones_fijas_hash
  }
}


