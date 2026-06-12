# Beacon bucket: holds endpoint.json, written by the home server and read
# by the edge Lambdas (KONZEPT section 9). Versioned, encrypted, private.

terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

resource "aws_s3_bucket" "beacon" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "beacon" {
  bucket = aws_s3_bucket.beacon.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "beacon" {
  bucket = aws_s3_bucket.beacon.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn == null ? "AES256" : "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}

resource "aws_s3_bucket_public_access_block" "beacon" {
  bucket = aws_s3_bucket.beacon.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enforce TLS at the resource level (least-privilege bucket policy,
# KONZEPT section 9): deny any credentialed plaintext-HTTP access.
data "aws_iam_policy_document" "deny_insecure_transport" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.beacon.arn,
      "${aws_s3_bucket.beacon.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "beacon" {
  bucket = aws_s3_bucket.beacon.id
  policy = data.aws_iam_policy_document.deny_insecure_transport.json

  depends_on = [aws_s3_bucket_public_access_block.beacon]
}

resource "aws_s3_bucket_lifecycle_configuration" "beacon" {
  bucket = aws_s3_bucket.beacon.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }
  }
}
