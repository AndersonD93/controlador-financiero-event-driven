output "catalogo_param_name" {
  value = aws_ssm_parameter.catalogo_conceptos.name
}

output "reglas_param_name" {
  value = aws_ssm_parameter.reglas_compensacion.name
}
