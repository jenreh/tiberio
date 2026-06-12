terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # Partial configuration: filled by deploy-aws.sh via backend.prod.hcl
  # (generated from the bootstrap phase / tfvars state_* variables).
  backend "s3" {}
}
