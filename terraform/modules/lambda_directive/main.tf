# Directive proxy Lambda (KONZEPT section 9): receives Smart Home directives
# from the Alexa skill, resolves the home endpoint via the S3 beacon and
# forwards the directive. Only the configured skill may invoke it.

terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

data "archive_file" "this" {
  type        = "zip"
  source_dir  = var.source_dir
  excludes    = var.source_excludes
  output_path = "${path.module}/build/${var.function_name}.zip"
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = var.role_arn
  runtime          = var.runtime
  handler          = var.handler
  filename         = data.archive_file.this.output_path
  source_code_hash = data.archive_file.this.output_base64sha256
  timeout          = var.timeout_seconds
  memory_size      = var.memory_size_mb

  environment {
    variables = {
      PANTAU_BEACON_BUCKET           = var.beacon_bucket_name
      PANTAU_BEACON_KEY              = var.beacon_object_key
      PANTAU_SHARED_SECRET_SSM_PARAM = var.shared_secret_ssm_param
    }
  }

  depends_on = [aws_cloudwatch_log_group.this]
}

resource "aws_lambda_permission" "alexa_smart_home" {
  statement_id       = "AllowAlexaSmartHome"
  action             = "lambda:InvokeFunction"
  function_name      = aws_lambda_function.this.function_name
  principal          = "alexa-connectedhome.amazon.com"
  event_source_token = var.alexa_skill_id
}
