#############################################
# Lambda Permissions (API Gateway / Pipes)
#############################################

locals {
  expanded_permissions = flatten([
    for name, cfg in var.mapping_lambda_permission_api : [
      for idx, arn in cfg.source_arn : {
        key          = "${name}-${idx}"
        lambda_name  = cfg.lambda_name
        principal    = cfg.principal
        source_arn   = arn
      }
    ]
  ])
}

resource "aws_lambda_permission" "lambda_permission" {
  for_each = {
    for p in local.expanded_permissions : p.key => p
  }

  statement_id  = "AllowExecution-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value.lambda_name
  principal     = each.value.principal
  source_arn    = each.value.source_arn
}
