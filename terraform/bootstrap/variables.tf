variable "aws_region" {
  description = "AWS region for the Terraform state bucket."
  type        = string
  default     = "eu-west-1"
}

variable "state_bucket_name" {
  description = <<-EOT
    Globally unique name of the S3 bucket that stores the Terraform state
    for the main (phase 2) configuration.
  EOT
  type        = string
  default     = "tiberio-tfstate"
}

variable "state_key" {
  description = "Object key of the Terraform state file inside the state bucket."
  type        = string
  default     = "terraform.tfstate"
}
