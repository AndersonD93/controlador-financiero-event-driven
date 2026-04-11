module "dynamo_tables_control_financiero" {
  source = "./modules/resources/dynamo_table"
  dynamo_tables = {
    HistoriaTarjetas = {
      table_name = "HistorialTarjetas"
      hash_key   = "trx_id"
      attributes = [
        { name = "trx_id",     type = "S" },
        { name = "franquicia", type = "S" }
      ]
      stream_enabled   = true
      stream_view_type = "NEW_AND_OLD_IMAGES"
      tags             = { Project = var.project }
      global_secondary_index = [
        {
          name            = "franquicia-index"
          hash_key        = "franquicia"
          projection_type = "ALL"
        }
      ]
    },
    ConceptosFijosObligaciones = {
      table_name = "ConceptosFijosObligaciones"
      hash_key   = "trx_id"
      attributes = [
        { name = "trx_id",            type = "S" },
        { name = "dominioFinanciero", type = "S" },
        { name = "corte",             type = "S" }  # <-- nuevo atributo requerido por el GSI
      ]
      stream_enabled   = true
      stream_view_type = "NEW_AND_OLD_IMAGES"
      tags             = { Project = var.project }
      global_secondary_index = [
        {
          name            = "dominioFinanciero-index"
          hash_key        = "dominioFinanciero"
          projection_type = "ALL"
        },
        {
          name            = "gsi-dominio-corte"
          hash_key        = "dominioFinanciero"
          range_key       = "corte"               # <-- el nuevo GSI
          projection_type = "ALL"
        }
      ]
    },
    HistoriaCuentasAltoRendimiento = {
      table_name = "HistoriaCuentasAltoRendimiento"
      hash_key   = "trx_id"
      attributes = [
        { name = "trx_id",            type = "S" },
        { name = "dominioFinanciero", type = "S" }
      ]
      stream_enabled   = true
      stream_view_type = "NEW_AND_OLD_IMAGES"
      tags             = { Project = var.project }
      global_secondary_index = [          # <-- cambiado de {} a []
        {
          name            = "dominioFinanciero-index"
          hash_key        = "dominioFinanciero"
          projection_type = "ALL"
        }
      ]
    },
    ConceptosFijosPersonal = {
      table_name = "ConceptosFijosPersonal"
      hash_key   = "trx_id"
      attributes = [
        { name = "trx_id",            type = "S" },
        { name = "dominioFinanciero", type = "S" },
        { name = "corte",             type = "S" }  # <-- nuevo atributo requerido por el GSI
      ]
      stream_enabled   = true
      stream_view_type = "NEW_AND_OLD_IMAGES"
      tags             = { Project = var.project }
      global_secondary_index = [
        {
          name            = "dominioFinanciero-index"
          hash_key        = "dominioFinanciero"
          projection_type = "ALL"
        },
        {
          name            = "gsi-dominio-corte"
          hash_key        = "dominioFinanciero"
          range_key       = "corte"               # <-- el nuevo GSI
          projection_type = "ALL"
        }
      ]
    },
    FlujoDeCaja = {
      table_name = "FlujoDeCaja"
      hash_key   = "Dominio-Corte"
      range_key  = "Tipo-Concepto"
      attributes = [
        { name = "Dominio-Corte",  type = "S" },
        { name = "Tipo-Concepto", type = "S" }
      ]
      tags = { Project = var.project }
      global_secondary_index = [          # <-- cambiado de {} a []
        {
          name            = "Dominio-Corte-index"
          hash_key        = "Dominio-Corte"
          projection_type = "ALL"
        }
      ]
    }
  }
}


module "table_permission" {
  source = "./modules/resources/dynamo_table/dynamo_permission"
  mapping_dynamo_permission = {
    HistoriaTarjetas = {
      table_arn               = module.dynamo_tables_control_financiero.dynamo_table_arn["HistoriaTarjetas"]
      roles_lambda_principals = [module.lambdas_backend_api.lambda_role_arns["MovimientosTarjetas"]]
    },
    ConceptosFijosObligaciones = {
      table_arn               = module.dynamo_tables_control_financiero.dynamo_table_arn["ConceptosFijosObligaciones"]
      roles_lambda_principals = [module.lambdas_backend_api.lambda_role_arns["ParametrizarConceptosAhorro"]]
    },
    HistoriaCuentasAltoRendimiento = {
      table_arn               = module.dynamo_tables_control_financiero.dynamo_table_arn["HistoriaCuentasAltoRendimiento"]
      roles_lambda_principals = [module.lambdas_backend_api.lambda_role_arns["MovimientosCuentasEInversiones"]]
    },
    ConceptosFijosPersonal = {
      table_arn               = module.dynamo_tables_control_financiero.dynamo_table_arn["ConceptosFijosPersonal"]
      roles_lambda_principals = [module.lambdas_backend_api.lambda_role_arns["ParametrizarConceptosAhorro"]]
    },
    FlujoDeCaja = {
      table_arn               = module.dynamo_tables_control_financiero.dynamo_table_arn["FlujoDeCaja"]
      roles_lambda_principals = [module.lambdas_backend_api.lambda_role_arns["ConsolidaMovimientosFinancieros"], module.lambdas_backend_api.lambda_role_arns["CierreMensual"]]
    }
  }
}
