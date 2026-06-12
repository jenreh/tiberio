# Pantau AWS edge (KONZEPT section 9): S3 beacon, least-privilege IAM,
# directive proxy Lambda and OAuth proxy behind an HTTP API.

provider "aws" {
  region = var.aws_region
}

locals {
  # Zipped as a whole per function (with excludes) so handler modules can
  # import the sibling shared/ package.
  lambda_source_dir = "${path.root}/../lambda"
}

# Shared secret for AWS-to-home HMAC authentication. The write-only argument
# keeps the secret out of the Terraform state and plan files entirely; bump
# shared_secret_version to push a rotated value.
resource "aws_ssm_parameter" "shared_secret" {
  name        = var.shared_secret_ssm_param
  description = "HMAC shared secret for AWS-to-home traffic."
  type        = "SecureString"

  value_wo         = var.shared_secret
  value_wo_version = var.shared_secret_version
}

module "s3_beacon" {
  source = "./modules/s3_beacon"

  bucket_name                        = var.beacon_bucket_name
  beacon_object_key                  = var.beacon_object_key
  kms_key_arn                        = var.beacon_kms_key_arn
  noncurrent_version_expiration_days = var.beacon_noncurrent_version_expiration_days
}

module "iam" {
  source = "./modules/iam"

  name_prefix                 = var.name_prefix
  beacon_object_arn           = module.s3_beacon.beacon_object_arn
  shared_secret_parameter_arn = aws_ssm_parameter.shared_secret.arn
  kms_key_arn                 = var.beacon_kms_key_arn
  create_home_publisher_user  = var.create_home_publisher_user
}

module "lambda_directive" {
  source = "./modules/lambda_directive"

  function_name           = "${var.name_prefix}-directive-proxy"
  source_dir              = local.lambda_source_dir
  runtime                 = var.lambda_runtime
  role_arn                = module.iam.directive_lambda_role_arn
  beacon_bucket_name      = module.s3_beacon.bucket_name
  beacon_object_key       = module.s3_beacon.beacon_object_key
  shared_secret_ssm_param = aws_ssm_parameter.shared_secret.name
  alexa_skill_id          = var.alexa_skill_id
}

module "apigw_oauth" {
  source = "./modules/apigw_oauth"

  api_name           = "${var.name_prefix}-oauth"
  function_name      = "${var.name_prefix}-oauth-proxy"
  source_dir         = local.lambda_source_dir
  runtime            = var.lambda_runtime
  role_arn           = module.iam.oauth_lambda_role_arn
  beacon_bucket_name = module.s3_beacon.bucket_name
  beacon_object_key  = module.s3_beacon.beacon_object_key
}
