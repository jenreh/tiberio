output "api_endpoint" {
  description = "Base endpoint of the OAuth HTTP API."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "authorize_url" {
  description = "Authorization URI for the Alexa account-linking configuration."
  value       = "${aws_apigatewayv2_api.this.api_endpoint}/oauth/authorize"
}

output "token_url" {
  description = "Access token URI for the Alexa account-linking configuration."
  value       = "${aws_apigatewayv2_api.this.api_endpoint}/oauth/token"
}

output "function_arn" {
  description = "ARN of the OAuth proxy Lambda function."
  value       = aws_lambda_function.this.arn
}
