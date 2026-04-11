module "ssm_reglas_flujo_caja" {
  source = "./modules/resources/ssm"

  prefix                = "flujo-caja"
  proyeccion_fija_path  = "${path.root}/templates/reglas/proyecciones_fijas.json"
  catalogo_path         = "${path.root}/templates/reglas/catalogo_financiero.json"
  reglas_path           = "${path.root}/templates/reglas/reglas_compensacion.json"
}

