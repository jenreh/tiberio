output "directive_lambda_role_arn" {
  description = "ARN of the directive Lambda execution role."
  value       = aws_iam_role.directive_lambda.arn
}

output "oauth_lambda_role_arn" {
  description = "ARN of the OAuth proxy Lambda execution role."
  value       = aws_iam_role.oauth_lambda.arn
}

output "home_publisher_user_name" {
  description = "Name of the home-server beacon publisher IAM user (or null)."
  value       = try(aws_iam_user.home_publisher[0].name, null)
}

output "home_publisher_user_arn" {
  description = "ARN of the home-server beacon publisher IAM user (or null)."
  value       = try(aws_iam_user.home_publisher[0].arn, null)
}
