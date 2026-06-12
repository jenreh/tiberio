variable "aws_region" {
  description = "AWS region for all edge resources."
  type        = string
  default     = "eu-west-1"
}

variable "name_prefix" {
  description = "Prefix for resource names (Lambdas, roles, API)."
  type        = string
  default     = "tiberio"
}

variable "alexa_skill_id" {
  description = "Alexa Smart Home skill ID allowed to invoke the directive Lambda."
  type        = string
}

variable "beacon_bucket_name" {
  description = "Globally unique name of the beacon S3 bucket."
  type        = string
  default     = "tiberio-beacon"
}

variable "beacon_object_key" {
  description = "Object key of the beacon document inside the bucket."
  type        = string
  default     = "endpoint.json"
}

variable "beacon_kms_key_arn" {
  description = "Optional KMS key ARN for the beacon bucket (null = SSE-S3/AES256)."
  type        = string
  default     = null
}

variable "beacon_noncurrent_version_expiration_days" {
  description = "Days after which noncurrent beacon object versions expire."
  type        = number
  default     = 30
}

variable "shared_secret" {
  description = <<-EOT
    HMAC shared secret for AWS-to-home traffic, stored as an SSM SecureString.
    Pass via TF_VAR_shared_secret or a tfvars file kept out of git.
  EOT
  type        = string
  sensitive   = true
}

variable "shared_secret_version" {
  description = <<-EOT
    Version counter for the write-only shared_secret value. Bump it to push
    a rotated secret to SSM; the secret itself never enters the state file.
  EOT
  type        = number
  default     = 1
}

variable "shared_secret_ssm_param" {
  description = "Name of the SSM SecureString parameter holding the shared secret."
  type        = string
  default     = "/tiberio/shared-secret"
}

variable "create_home_publisher_user" {
  description = "Create the IAM user the home server uses to publish the beacon."
  type        = bool
  default     = true
}

variable "lambda_runtime" {
  description = "Runtime for both edge Lambda functions."
  type        = string
  default     = "python3.13"
}

# Consumed by deploy-aws.sh / bootstrap; declared here so a shared tfvars file
# does not trigger undeclared-variable warnings in phase 2.
variable "state_bucket_name" {
  description = "Name of the S3 bucket holding the Terraform state (bootstrap)."
  type        = string
  default     = "tiberio-tfstate"
}
