# Consumed by deploy-aws.sh (written to backend_config.json after phase 1).
output "backend_configuration" {
  description = "S3 backend settings for the main (phase 2) configuration."
  value = {
    bucket       = aws_s3_bucket.tfstate.bucket
    key          = var.state_key
    region       = var.aws_region
    encrypt      = true
    use_lockfile = true
  }
}
