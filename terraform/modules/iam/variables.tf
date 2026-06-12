variable "name_prefix" {
  description = "Prefix for all IAM resource names."
  type        = string
  default     = "pantau-alexa"
}

variable "beacon_object_arn" {
  description = "ARN of the single beacon object (bucket-arn/endpoint.json)."
  type        = string
}

variable "shared_secret_parameter_arn" {
  description = "ARN of the SSM SecureString parameter with the shared secret."
  type        = string
}

variable "kms_key_arn" {
  description = "Optional KMS key ARN encrypting the beacon bucket (null = SSE-S3)."
  type        = string
  default     = null
}

variable "create_home_publisher_user" {
  description = <<-EOT
    Create the IAM user the home server uses to publish the beacon object.
    Access keys are intentionally NOT managed by Terraform; create them
    manually so the secret never enters the state file.
  EOT
  type        = bool
  default     = true
}
