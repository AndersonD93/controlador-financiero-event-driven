locals {
  catalogo_cuentas_value      = file("${path.module}/../../../templates/reglas/catalogo_cuentas.json")
  catalogo_conceptos_value    = file("${path.module}/../../../templates/reglas/catalogo_conceptos.json")
  reglas_compensacion_value   = file("${path.module}/../../../templates/reglas/reglas_compensacion.json")

  catalogo_cuentas_hash       = filesha256("${path.module}/../../../templates/reglas/catalogo_cuentas.json")
  catalogo_conceptos_hash     = filesha256("${path.module}/../../../templates/reglas/catalogo_conceptos.json")
  reglas_compensacion_hash    = filesha256("${path.module}/../../../templates/reglas/reglas_compensacion.json")
}



resource "aws_ssm_parameter" "catalogo_conceptos" {
  name        = "/${var.prefix}/catalogo-conceptos"
  description = "Catálogo de conceptos válidos para flujo de caja"
  type        = "String"
  tier        = "Standard"
  value       = local.catalogo_conceptos_value
  overwrite   = true

  tags = {
    proyecto     = "flujo-caja"
    tipo         = "catalogo-conceptos"
    content_hash = local.catalogo_conceptos_hash
  }
}


resource "aws_ssm_parameter" "reglas_compensacion" {
  name        = "/${var.prefix}/reglas-compensacion"
  description = "Reglas de compensación para flujo de caja"
  type        = "String"
  tier        = "Standard"
  value       = local.reglas_compensacion_value
  overwrite   = true

  tags = {
    proyecto     = "flujo-caja"
    tipo         = "reglas-compensacion"
    content_hash = local.reglas_compensacion_hash
  }
}


resource "aws_ssm_parameter" "catalogo_cuentas" {
  name        = "/${var.prefix}/catalogo-cuentas"
  description = "Catálogo de cuentas válidas por dominio financiero"
  type        = "String"
  tier        = "Standard"
  value       = local.catalogo_cuentas_value
  overwrite   = true

  tags = {
    proyecto     = "flujo-caja"
    tipo         = "catalogo-cuentas"
    content_hash = local.catalogo_cuentas_hash
  }
}

