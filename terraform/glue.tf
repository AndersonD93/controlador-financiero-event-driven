resource "aws_iam_role" "glue_role" {
  name = "${var.project}-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "glue_policy" {
  role = aws_iam_role.glue_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:DescribeTable"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          "arn:aws:s3:::${module.s3.bucket_names["reporting"]}",
          "arn:aws:s3:::${module.s3.bucket_names["scripts"]}/*",
          "arn:aws:s3:::${module.s3.bucket_names["reporting"]}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:*"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_glue_job" "export_dynamo_to_s3" {
  name     = "${var.project}-export-dynamo"
  role_arn = aws_iam_role.glue_role.arn

  command {
    name            = "glueetl"
    script_location = "s3://${module.s3.bucket_names["scripts"]}/${aws_s3_object.glue_export_script.key}"
    python_version  = "3"
  }

  glue_version = "4.0"
  worker_type  = "G.1X"
  number_of_workers = 2

  default_arguments = {
    "--job-language"        = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"     = ""
    "--DYNAMO_TABLE"       = module.dynamo_tables_control_financiero.dynamo_table_name["FlujoDeCaja"]
    "--OUTPUT_S3_PATH"     = "s3://${module.s3.bucket_names["reporting"]}/reports/"
  }
}

resource "aws_s3_object" "glue_export_script" {
  bucket = module.s3.bucket_names["scripts"]
  key    = "scripts/export_dynamo_to_s3.py"

  source = "${path.module}/templates/glue_code/export_dynamo_to_s3.py"

  etag = filemd5("${path.module}/templates/glue_code/export_dynamo_to_s3.py")

  content_type = "text/x-python"
}



