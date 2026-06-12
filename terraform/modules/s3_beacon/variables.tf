variable "bucket_name" {
  description = "Globally unique name of the beacon S3 bucket."
  type        = string
  default     = "pantau-alexa-beacon"
}

variable "beacon_object_key" {
  description = "Object key of the beacon document inside the bucket."
  type        = string
  default     = "endpoint.json"
}

variable "kms_key_arn" {
  description = <<-EOT
    Optional KMS key ARN for server-side encryption. When null, SSE-S3
    (AES256) is used instead of SSE-KMS.
  EOT
  type        = string
  default     = null
}

variable "noncurrent_version_expiration_days" {
  description = "Days after which noncurrent beacon object versions expire."
  type        = number
  default     = 30
}
