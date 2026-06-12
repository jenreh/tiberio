output "function_arn" {
  description = "ARN of the directive Lambda (skill default endpoint)."
  value       = aws_lambda_function.this.arn
}

output "function_name" {
  description = "Name of the directive Lambda function."
  value       = aws_lambda_function.this.function_name
}
