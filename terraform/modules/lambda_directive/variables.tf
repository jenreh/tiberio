variable "function_name" {
  description = "Name of the directive proxy Lambda function."
  type        = string
  default     = "pantau-alexa-directive-proxy"
}

variable "source_dir" {
  description = <<-EOT
    Path to the Lambda source root (the repository lambda/ directory). It is
    zipped as a whole so the shared/ package ends up next to the handler.
  EOT
  type        = string
}

variable "source_excludes" {
  description = "Glob patterns (relative to source_dir) excluded from the package."
  type        = list(string)
  default     = ["oauth_proxy/**", "**/__pycache__/**", "**/*.pyc"]
}

variable "handler" {
  description = "Lambda handler entrypoint."
  type        = string
  default     = "directive_proxy.handler.handler"
}

variable "runtime" {
  description = "Lambda runtime identifier."
  type        = string
  default     = "python3.13"
}

variable "timeout_seconds" {
  description = "Lambda timeout. Must stay below the 8 s Alexa directive limit."
  type        = number
  default     = 7
}

variable "memory_size_mb" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 256
}

variable "role_arn" {
  description = "ARN of the Lambda execution role (from the iam module)."
  type        = string
}

variable "beacon_bucket_name" {
  description = "Beacon bucket name (PANTAU_BEACON_BUCKET)."
  type        = string
}

variable "beacon_object_key" {
  description = "Beacon object key (PANTAU_BEACON_KEY)."
  type        = string
}

variable "shared_secret_ssm_param" {
  description = "SSM parameter name with the shared secret (PANTAU_SHARED_SECRET_SSM_PARAM)."
  type        = string
}

variable "alexa_skill_id" {
  description = "Alexa Smart Home skill ID allowed to invoke the function."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the function."
  type        = number
  default     = 14
}
