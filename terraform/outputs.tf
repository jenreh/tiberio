output "directive_lambda_arn" {
  description = "ARN of the directive Lambda (Alexa skill default endpoint)."
  value       = module.lambda_directive.function_arn
}

output "oauth_authorize_url" {
  description = "Authorization URI for the Alexa account-linking configuration."
  value       = module.apigw_oauth.authorize_url
}

output "oauth_token_url" {
  description = "Access token URI for the Alexa account-linking configuration."
  value       = module.apigw_oauth.token_url
}

output "beacon_bucket_name" {
  description = "Name of the S3 beacon bucket (endpoint.json)."
  value       = module.s3_beacon.bucket_name
}

output "home_publisher_user_name" {
  description = "IAM user the home server uses to publish the beacon (or null)."
  value       = module.iam.home_publisher_user_name
}

# Consumed by deploy-aws.sh after a successful phase-2 apply.
output "deployment_summary" {
  description = "Key values needed for the Alexa skill configuration."
  value = {
    directive_lambda_arn = module.lambda_directive.function_arn
    oauth_authorize_url  = module.apigw_oauth.authorize_url
    oauth_token_url      = module.apigw_oauth.token_url
    beacon_bucket_name   = module.s3_beacon.bucket_name
    beacon_object_key    = module.s3_beacon.beacon_object_key
    shared_secret_param  = aws_ssm_parameter.shared_secret.name
  }
}
