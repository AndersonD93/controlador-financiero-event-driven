module "lambdas_backend_api" {
  source = "./modules/resources/lambda"
  lambda_map = {
    MovimientosCuentasEInversiones = {
      lambda_name = "MovimientosCuentasEInversiones"
      handler     = "MovimientosCuentasEInversiones.lambda_handler"
      runtime     = "python3.12"
      layers = [
        aws_lambda_layer_version.python_deps.arn
      ]
      environment_variables = {
        "cuentas_alto_rendimiento_table" = module.dynamo_tables_control_financiero.dynamo_table_name["HistoriaCuentasAltoRendimiento"]
        "EVENT_BUS_NAME"                 = aws_cloudwatch_event_bus.bus_financiero.name
      }
    },
    ParametrizarConceptosAhorro = {
      lambda_name = "ParametrizarConceptosAhorro"
      handler     = "ParametrizarConceptosAhorro.lambda_handler"
      runtime     = "python3.12"
      layers = [
        aws_lambda_layer_version.python_deps.arn
      ]
      environment_variables = {
        "conceptos_fijos_table"         = module.dynamo_tables_control_financiero.dynamo_table_name["ConceptosFijosObligaciones"]
        "conceptos_fijos_persona_table" = module.dynamo_tables_control_financiero.dynamo_table_name["ConceptosFijosPersonal"]
        "EVENT_BUS_NAME"                = aws_cloudwatch_event_bus.bus_financiero.name
      }
    },
    MovimientosTarjetas = {
      lambda_name = "MovimientosTarjetas"
      handler     = "MovimientosTarjetas.lambda_handler"
      runtime     = "python3.12"
      layers = [
        aws_lambda_layer_version.python_deps.arn
      ]
      environment_variables = {
        "historia_tarjetas_table" = module.dynamo_tables_control_financiero.dynamo_table_name["HistoriaTarjetas"]
        "EVENT_BUS_NAME"          = aws_cloudwatch_event_bus.bus_financiero.name
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
      layers = [
        aws_lambda_layer_version.python_deps.arn
      ]
      environment_variables = {
        "flujo_caja_table" = module.dynamo_tables_control_financiero.dynamo_table_name["FlujoDeCaja"]
      }
    },
    ProyeccionesFijas = {
      lambda_name = "ProyeccionesFijas"
      handler     = "ProyeccionesFijas.lambda_handler"
      runtime     = "python3.12"
      layers = [
        aws_lambda_layer_version.python_deps.arn
      ]
      environment_variables = {
        "conceptos_fijos_table"         = module.dynamo_tables_control_financiero.dynamo_table_name["ConceptosFijosObligaciones"]
        "conceptos_fijos_persona_table" = module.dynamo_tables_control_financiero.dynamo_table_name["ConceptosFijosPersonal"]
      }
    },
    EmbeddingLambda = {
      lambda_name = "EmbeddingLambda"
      handler     = "EmbeddingLambda.lambda_handler"
      runtime     = "python3.12"
      timeout     = 30
      environment_variables = {
        "VECTOR_BUCKET" = var.vector_bucket_name
        "EMBED_MODEL"   = "amazon.titan-embed-text-v1"
        "VECTOR_INDEX"  = "rag-index"
      }
    },
    WebhookHandler = {
      lambda_name = "WebhookHandler"
      handler     = "WebhookHandler.lambda_handler"
      runtime     = "python3.12"
      layers = [
        aws_lambda_layer_version.python_deps.arn
      ]
      timeout = 30
      environment_variables = {
        "SLACK_SECRET_NAME"   = aws_secretsmanager_secret.slack_webhook_secret.name,
        "ROUTER_FUNCTION_ARN" = module.lambdas_interpretador.lambda_arns["InterpretadorRouters"],
        "SLACK_BOT_TOKEN"     = aws_secretsmanager_secret.slack_bot_token.name,
        "QUERY_FUNCTION_ARN" = module.lambdas_QueryRagEmbedding.lambda_arns["QueryRagEmbedding"]
      }
    },
    NotificadorSlack = {
      lambda_name = "NotificadorSlack"
      handler     = "NotificadorSlack.lambda_handler"
      runtime     = "python3.12"
      timeout = 30
      environment_variables = {
        "SLACK_SECRET_NAME"   = aws_secretsmanager_secret.slack_webhook_secret.name,
        "SLACK_BOT_TOKEN"     = aws_secretsmanager_secret.slack_bot_token.name
      }
    },
    EnvioEmail = {
      lambda_name = "EnvioEmail"
      handler     = "EnvioEmail.lambda_handler"
      runtime     = "python3.12"
      timeout = 30
      environment_variables = {
        "SES_SENDER"         = data.aws_sesv2_email_identity.sender.email_identity,
        "SES_RECIPIENT"      = data.aws_sesv2_email_identity.recipient.email_identity,
        "SES_REGION"         = var.region
        "URL_EXPIRATION_SEC" =  "7200"
      }
    }
  }
}

module "lambdas_interpretador" {
  source = "./modules/resources/lambda"
  lambda_map = {
    InterpretadorRouters = {
      lambda_name = "InterpretadorRouters"
      handler     = "InterpretadorRouters.lambda_handler"
      runtime     = "python3.12"
      timeout     = 30
      environment_variables = {
        "EVENT_BUS_NAME"=  aws_cloudwatch_event_bus.bus_financiero.name
      }
    }
  }
}

module "lambdas_QueryRagEmbedding" {
  source = "./modules/resources/lambda"
  lambda_map = {
    QueryRagEmbedding = {
      lambda_name = "QueryRagEmbedding"
      handler     = "QueryRagEmbedding.lambda_handler"
      runtime     = "python3.12"
      timeout     = 30
      environment_variables = {
        "VECTOR_BUCKET" = var.vector_bucket_name
        "EMBED_MODEL"   = "amazon.titan-embed-text-v1"
        "LLM_MODEL"     = "anthropic.claude-3-sonnet-20240229-v1:0"
        "VECTOR_INDEX"  = "rag-index",
        "SLACK_BOT_TOKEN" = aws_secretsmanager_secret.slack_bot_token.name
      }
    }
  }
}

module "lambda_permission_api" {
  source = "./modules/resources/lambda/lambda_permission"
  mapping_lambda_permission_api = {

    "MovimientosCuentasEInversiones" = {
      lambda_name = module.lambdas_backend_api.lambda_name["MovimientosCuentasEInversiones"]
      source_arn  = [module.api_resource_MovimientosCuentasEInversiones.method_arn["post_MovimientosCuentasEInversiones"]]
      principal   = "apigateway.amazonaws.com"
    },
    "MovimientosCuentasEInversiones_events" = {
      lambda_name = module.lambdas_backend_api.lambda_name["MovimientosCuentasEInversiones"]
      source_arn  = [aws_cloudwatch_event_rule.movimiento_general.arn]
      principal   = "events.amazonaws.com"
    },
    "ParametrizarConceptosAhorro" = {
      lambda_name = module.lambdas_backend_api.lambda_name["ParametrizarConceptosAhorro"]
      source_arn  = [module.api_resource_ParametrizarConceptosAhorro.method_arn["post_ParametrizarConceptosAhorro"]]
      principal   = "apigateway.amazonaws.com"
    },
    "ParametrizarConceptosAhorro_events" = {
      lambda_name = module.lambdas_backend_api.lambda_name["ParametrizarConceptosAhorro"]
      source_arn  = [aws_cloudwatch_event_rule.movimiento_proyeccion.arn]
      principal   = "events.amazonaws.com"
    },
    "MovimientosTarjetas" = {
      lambda_name = module.lambdas_backend_api.lambda_name["MovimientosTarjetas"]
      source_arn  = [module.api_resource_MovimientosTarjetas.method_arn["MovimientosTarjetas_post"]]
      principal   = "apigateway.amazonaws.com"
    },
    "MovimientosTarjetas_events" = {
      lambda_name = module.lambdas_backend_api.lambda_name["MovimientosTarjetas"]
      source_arn  = [aws_cloudwatch_event_rule.movimiento_tarjeta.arn]
      principal   = "events.amazonaws.com"
    },
    "ConsolidaMovimientosFinancieros" = {
      lambda_name = module.lambdas_backend_api.lambda_name["ConsolidaMovimientosFinancieros"]
      source_arn = [aws_pipes_pipe.dynamo_to_lambda_historia_tarjetas.arn,
        aws_pipes_pipe.dynamo_to_lambda_conceptos_personal.arn,
        aws_pipes_pipe.dynamo_to_lambda_conceptos_obligaciones.arn,
      aws_pipes_pipe.dynamo_to_lambda_cuentas_rendimiento.arn]
      principal = "pipes.amazonaws.com"
    },
    "CierreMensual" = {
      lambda_name = module.lambdas_backend_api.lambda_name["CierreMensual"]
      source_arn  = [aws_cloudwatch_event_rule.mensual.arn]
      principal   = "events.amazonaws.com"
    },
    "ProyeccionesFijas" = {
      lambda_name = module.lambdas_backend_api.lambda_name["ProyeccionesFijas"]
      source_arn  = [aws_cloudwatch_event_rule.mensual.arn]
      principal   = "events.amazonaws.com"
    },
    "EmbeddingLambda" = {
      lambda_name = module.lambdas_backend_api.lambda_name["EmbeddingLambda"]
      source_arn  = [module.s3.bucket_arns["reporting"]]
      principal   = "s3.amazonaws.com"
    },
    "QueryRagEmbedding" = {
      lambda_name = module.lambdas_QueryRagEmbedding.lambda_name["QueryRagEmbedding"]
      source_arn  = [module.api_resource_QueryRagEmbedding.method_arn["QueryRagEmbedding_post"]]
      principal   = "apigateway.amazonaws.com"
    },
    "WebhookHandler" = {
      lambda_name = module.lambdas_backend_api.lambda_name["WebhookHandler"]
      source_arn  = [module.api_resource_SlackEvents.method_arn["post_SlackEvents"]]
      principal   = "apigateway.amazonaws.com"
    },
    "NotificadorSlack" = {
      lambda_name = module.lambdas_backend_api.lambda_name["NotificadorSlack"]
      source_arn  = [aws_cloudwatch_event_rule.notificacion_slack.arn]
      principal   = "events.amazonaws.com"
    },
    "EnvioEmail" = {
      lambda_name = module.lambdas_backend_api.lambda_name["EnvioEmail"]
      source_arn  = [module.s3.bucket_arns["reporting"]]
      principal   = "s3.amazonaws.com"
    }
  }
}


data "archive_file" "catalogo_financiero_layer_zip" {
  type        = "zip"
  source_dir  = "${path.root}/templates/layer"
  output_path = "${path.root}/templates/layer/catalogo_financiero_layer-${md5(file("${path.root}/templates/layer/python/catalogo_financiero.py"))}.zip"
}


resource "aws_lambda_layer_version" "python_deps" {
  layer_name          = "catalogo-financiero-deps"
  filename            = data.archive_file.catalogo_financiero_layer_zip.output_path
  source_code_hash    = data.archive_file.catalogo_financiero_layer_zip.output_base64sha256
  compatible_runtimes = ["python3.11", "python3.12"]

  description = "Funciones transversales para al caché, validaciones de catalogos"
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
