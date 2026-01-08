module "ssm_reglas_flujo_caja" {
  source = "./modules/resources/ssm"

  prefix         = "flujo-caja"
  catalogo_path  = "${path.root}/templates/reglas/catalogo_conceptos.json"
  reglas_path    = "${path.root}/templates/reglas/reglas_compensacion.json"
  catalogo_cuentas_path ="${path.root}/templates/reglas/catalogo_cuentas.json"
}
