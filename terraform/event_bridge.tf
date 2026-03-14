#Rol para la canalización de Event Bridge
resource "aws_iam_role" "pipe_role" {
  name = "eventbridge-pipe-dynamo-role"

  assume_role_policy = jsonencode({
  Version = "2012-10-17"
  Statement = [{
    Effect = "Allow"
    Principal = {
      Service = "pipes.amazonaws.com"
    }
    Action = "sts:AssumeRole"
  }]
})
}

#Permisos del rol

resource "aws_iam_role_policy" "pipe_policy" {
  role = aws_iam_role.pipe_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams"
        ]
        Resource = [
            module.dynamo_tables_control_financiero.dynamo_table_stream_arn["HistoriaTarjetas"],
            module.dynamo_tables_control_financiero.dynamo_table_stream_arn["ConceptosFijosObligaciones"],
            module.dynamo_tables_control_financiero.dynamo_table_stream_arn["HistoriaCuentasAltoRendimiento"],
            module.dynamo_tables_control_financiero.dynamo_table_stream_arn["ConceptosFijosPersonal"]
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = module.lambdas_backend_api.lambda_arns["ConsolidaMovimientosFinancieros"]
      }
    ]
  })
}

#Event Bridge Canalización
resource "aws_pipes_pipe" "dynamo_to_lambda_historia_tarjetas" {
  name     = "pipe-dynamo-movimientos-tarjetas"
  role_arn = aws_iam_role.pipe_role.arn
  source   = module.dynamo_tables_control_financiero.dynamo_table_stream_arn["HistoriaTarjetas"]
  target   = module.lambdas_backend_api.lambda_arns["ConsolidaMovimientosFinancieros"]

  source_parameters {
    dynamodb_stream_parameters {
      starting_position = "LATEST"
      batch_size        = 1
    }

    filter_criteria {
      filter {
        pattern = jsonencode({
          eventName = ["INSERT", "MODIFY"]
        })
      }
    }
  }
}

resource "aws_pipes_pipe" "dynamo_to_lambda_conceptos_personal" {
  name     = "pipe-dynamo-movimientos-conceptos-personal"
  role_arn = aws_iam_role.pipe_role.arn
  source   = module.dynamo_tables_control_financiero.dynamo_table_stream_arn["ConceptosFijosPersonal"]
  target   = module.lambdas_backend_api.lambda_arns["ConsolidaMovimientosFinancieros"]

  source_parameters {
    dynamodb_stream_parameters {
      starting_position = "LATEST"
      batch_size        = 1
    }

    filter_criteria {
      filter {
        pattern = jsonencode({
          eventName = ["INSERT", "MODIFY"]
        })
      }
    }
  }
}

resource "aws_pipes_pipe" "dynamo_to_lambda_conceptos_obligaciones" {
  name     = "pipe-dynamo-movimientos-conceptos-obligaciones"
  role_arn = aws_iam_role.pipe_role.arn
  source   = module.dynamo_tables_control_financiero.dynamo_table_stream_arn["ConceptosFijosObligaciones"]
  target   = module.lambdas_backend_api.lambda_arns["ConsolidaMovimientosFinancieros"]

  source_parameters {
    dynamodb_stream_parameters {
      starting_position = "LATEST"
      batch_size        = 1
    }

    filter_criteria {
      filter {
        pattern = jsonencode({
          eventName = ["INSERT", "MODIFY"]
        })
      }
    }
  }
}

resource "aws_pipes_pipe" "dynamo_to_lambda_cuentas_rendimiento" {
  name     = "pipe-dynamo-movimientos-cuentas-rendimiento"
  role_arn = aws_iam_role.pipe_role.arn
  source   = module.dynamo_tables_control_financiero.dynamo_table_stream_arn["HistoriaCuentasAltoRendimiento"]
  target   = module.lambdas_backend_api.lambda_arns["ConsolidaMovimientosFinancieros"]

  source_parameters {
    dynamodb_stream_parameters {
      starting_position = "LATEST"
      batch_size        = 1
    }

    filter_criteria {
      filter {
        pattern = jsonencode({
          eventName = ["INSERT", "MODIFY"]
        })
      }
    }
  }
}

resource "aws_cloudwatch_event_rule" "mensual" {
  name                = "cierre-mensual-flujo-caja"
  schedule_expression = "cron(0 0 1 * ? *)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.mensual.name
  target_id = "cierre-mensual"
  arn       = module.lambdas_backend_api.lambda_arns["CierreMensual"]
}

resource "aws_cloudwatch_event_target" "lambda_target_proyecciones_fijas" {
  rule      = aws_cloudwatch_event_rule.mensual.name
  target_id = "proyecciones-fijas"
  arn       = module.lambdas_backend_api.lambda_arns["ProyeccionesFijas"]
}

resource "aws_cloudwatch_event_rule" "semantic_router_update" {

  name = "semantic-router-update"

  event_pattern = jsonencode({
    source = ["aws.ssm"]
    "detail-type" = ["Parameter Store Change"]
    detail = {
      name = ["/ai-router/intents"]
      operation = ["Create","Update"]
    }
  })
}

resource "aws_cloudwatch_event_target" "invoke_update_embeddings" {

  rule = aws_cloudwatch_event_rule.semantic_router_update.name
  arn  =  module.lambdas_backend_api.lambda_arns["ActualizaEmbeddings"]
}
