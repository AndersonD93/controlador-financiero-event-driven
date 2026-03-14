module "ssm_reglas_flujo_caja" {
  source = "./modules/resources/ssm"

  prefix                = "flujo-caja"
  proyeccion_fija_path  = "${path.root}/templates/reglas/proyecciones_fijas.json"
  catalogo_path         = "${path.root}/templates/reglas/catalogo_financiero.json"
  reglas_path           = "${path.root}/templates/reglas/reglas_compensacion.json"
}


resource "aws_ssm_parameter" "semantic_router_rules" {

  name = "/ai-router/intents"
  type = "String"

  value = jsonencode({
    hash = local.intents_hash
    config = jsondecode(templatefile(local.intents_template, {
      lambda_contabilizar_proyecciones = module.lambdas_backend_api.lambda_name["ParametrizarConceptosAhorro"]
      lambda_movimiento_cuentas_inversiones = module.lambdas_backend_api.lambda_name["MovimientosCuentasEInversiones"]
      lambda_movimiento_tarjetas = module.lambdas_backend_api.lambda_name["MovimientosTarjetas"]
      lambda_consulta_lenguaje = module.lambdas_backend_api.lambda_name["QueryRagEmbedding"]
    }))
  })
}
