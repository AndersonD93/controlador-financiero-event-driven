#LAMBDAS
module "lambdas_backend_api" {
  source = "./modules/resources/lambda"
  lambda_map = {
    MovimientosCuentasAltoRendimiento = {
      lambda_name = "MovimientosCuentasAltoRendimiento"
      handler     = "MovimientosCuentasAltoRendimiento.lambda_handler"
      runtime     = "python3.12"
      environment_variables = {
        "cuentas_alto_rendimiento_table" = module.dynamo_tables_control_financiero.dynamo_table_name["HistoriaCuentasAltoRendimiento"]
      }
    },
    ParametrizarConceptosAhorro = {
      lambda_name = "ParametrizarConceptosAhorro"
      handler     = "ParametrizarConceptosAhorro.lambda_handler"
      runtime     = "python3.12"
      environment_variables = {
        "conceptos_fijos_table" = module.dynamo_tables_control_financiero.dynamo_table_name["ConceptosFijosObligaciones"]
        "conceptos_fijos_persona_table" = module.dynamo_tables_control_financiero.dynamo_table_name["ConceptosFijosPersonal"]
      }
    },
    MovimientosTarjetas = {
      lambda_name = "MovimientosTarjetas"
      handler     = "MovimientosTarjetas.lambda_handler"
      runtime     = "python3.12"
      environment_variables = {
        "historia_tarjetas_table" = module.dynamo_tables_control_financiero.dynamo_table_name["HistoriaTarjetas"]
      }
    },
    ConsolidaMovimientosFinancieros = {
      lambda_name = "ConsolidaMovimientosFinancieros"
      handler     = "ConsolidaMovimientosFinancieros.lambda_handler"
      runtime     = "python3.12"
      environment_variables = {
        "flujo_caja_table" = module.dynamo_tables_control_financiero.dynamo_table_name["FlujoDeCaja"]
      }
    },
    CierreMensual = {
      lambda_name = "CierreMensual"
      handler     = "CierreMensual.lambda_handler"
      runtime     = "python3.12"
      environment_variables = {
        "flujo_caja_table" = module.dynamo_tables_control_financiero.dynamo_table_name["FlujoDeCaja"]
      }
    }
  }
}


module "lambda_permission_api" {
  source = "./modules/resources/lambda/lambda_permission"
  mapping_lambda_permission_api = {
    
    "MovimientosCuentasAltoRendimiento" = {
      lambda_name = module.lambdas_backend_api.lambda_name["MovimientosCuentasAltoRendimiento"]
      source_arn  = [module.api_resource_MovimientosCuentasAltoRendimiento.method_arn["post_MovimientosCuentasAltoRendimiento"]]
      principal   = "apigateway.amazonaws.com"
    },
    "ParametrizarConceptosAhorro" = {
      lambda_name = module.lambdas_backend_api.lambda_name["ParametrizarConceptosAhorro"]
      source_arn  = [module.api_resource_ParametrizarConceptosAhorro.method_arn["post_ParametrizarConceptosAhorro"]]
      principal   = "apigateway.amazonaws.com"
    },
    "MovimientosTarjetas" = {
      lambda_name = module.lambdas_backend_api.lambda_name["MovimientosTarjetas"]
      source_arn  = [module.api_resource_MovimientosTarjetas.method_arn["MovimientosTarjetas_post"]]
      principal   = "apigateway.amazonaws.com"
    },
    "ConsolidaMovimientosFinancieros" = {
      lambda_name = module.lambdas_backend_api.lambda_name["ConsolidaMovimientosFinancieros"]
      source_arn  = [aws_pipes_pipe.dynamo_to_lambda_historia_tarjetas.arn,
                  aws_pipes_pipe.dynamo_to_lambda_conceptos_personal.arn,
                  aws_pipes_pipe.dynamo_to_lambda_conceptos_obligaciones.arn,
                  aws_pipes_pipe.dynamo_to_lambda_cuentas_rendimiento.arn]
      principal   = "pipes.amazonaws.com"
    },
    "CierreMensual" = {
      lambda_name = module.lambdas_backend_api.lambda_name["CierreMensual"]
      source_arn  = [aws_cloudwatch_event_rule.mensual.arn]
      principal   = "events.amazonaws.com"
    }  
  }
}
/*
resource "aws_lambda_event_source_mapping" "dynamodb_stream_trigger" {
  event_source_arn  = module.dynamo_tables_bets_manager.dynamo_table_stream_arn
  function_name     = module.lambdas_backend_api.lambda_arns["recalculate_score"]
  enabled           = true
  batch_size        = 100
  starting_position = "LATEST"
}
*/