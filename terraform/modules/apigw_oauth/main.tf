# OAuth proxy (KONZEPT section 9): stable API Gateway URLs for the Alexa
# account-linking configuration; a catch-all route forwards /oauth/* to the
# proxy Lambda, which relays to the home server resolved via the S3 beacon.

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

  # The OAuth proxy never signs requests — it must not receive the shared
  # secret (least privilege, KONZEPT section 9).
  environment {
    variables = {
      PANTAU_BEACON_BUCKET = var.beacon_bucket_name
      PANTAU_BEACON_KEY    = var.beacon_object_key
    }
  }

  depends_on = [aws_cloudwatch_log_group.this]
}

resource "aws_apigatewayv2_api" "this" {
  name          = var.api_name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "oauth" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.this.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "oauth_proxy" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /oauth/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.oauth.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
