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


resource "aws_cloudwatch_event_bus" "bus_financiero" {
  name = "bus-financiero"
}

resource "aws_cloudwatch_event_rule" "movimiento_general" {
  name           = "rule-movimiento-general"
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name

  event_pattern = jsonencode({
    "source": ["app.financiero"],
    "detail-type": ["movimiento.general.registrado"]
  })
}

resource "aws_cloudwatch_event_target" "target_movimiento_general" {
  rule           = aws_cloudwatch_event_rule.movimiento_general.name
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name
  target_id      = "lambda-movimiento-general"
  arn            = module.lambdas_backend_api.lambda_arns["MovimientosCuentasEInversiones"]
}

resource "aws_cloudwatch_event_rule" "movimiento_tarjeta" {
  name           = "rule-movimiento-tarjeta"
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name

  event_pattern = jsonencode({
    "source": ["app.financiero"],
    "detail-type": ["movimiento.tarjeta.registrado"]
  })
}

resource "aws_cloudwatch_event_target" "target_movimiento_tarjeta" {
  rule           = aws_cloudwatch_event_rule.movimiento_tarjeta.name
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name
  target_id      = "lambda-movimiento-tarjeta"
  arn            = module.lambdas_backend_api.lambda_arns["MovimientosTarjetas"]
}

resource "aws_cloudwatch_event_rule" "movimiento_proyeccion" {
  name           = "rule-movimiento-proyeccion"
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name

  event_pattern = jsonencode({
    "source": ["app.financiero"],
    "detail-type": ["proyeccion.registrado"]
  })
}

resource "aws_cloudwatch_event_target" "target_movimiento_proyeccion" {
  rule           = aws_cloudwatch_event_rule.movimiento_proyeccion.name
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name
  target_id      = "lambda-movimiento-proyeccion"
  arn            = module.lambdas_backend_api.lambda_arns["ParametrizarConceptosAhorro"]
}


resource "aws_cloudwatch_event_rule" "notificacion_slack" {
  name           = "notificacion-slack-ingesta"
  description    = "Dispara la lambda de Slack ante eventos de ingesta financiera"
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name

  event_pattern = jsonencode({
    source      = ["app.financiero"]
    "detail-type" = [
      "movimiento.tarjeta.confirmado",
      "movimiento.cuenta.confirmado",
      "concepto.fijo.confirmado"
    ]
  })
}

resource "aws_cloudwatch_event_target" "slack_target" {
  rule           = aws_cloudwatch_event_rule.notificacion_slack.name
  event_bus_name = aws_cloudwatch_event_bus.bus_financiero.name
  target_id      = "lambda-notificador-slack"
  arn            = module.lambdas_backend_api.lambda_arns["NotificadorSlack"]
}
