# Least-privilege IAM (KONZEPT section 9): both Lambdas may only read the
# single beacon object; only the directive Lambda may read the shared-secret
# parameter; the home server may only write that one object.

terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

locals {
  lambda_basic_execution_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Beacon read access — shared by both Lambda roles.
data "aws_iam_policy_document" "beacon_read" {
  statement {
    sid       = "ReadBeaconObject"
    actions   = ["s3:GetObject"]
    resources = [var.beacon_object_arn]
  }

  # SSE-KMS: reading the beacon object requires decrypting with the bucket key.
  dynamic "statement" {
    for_each = var.kms_key_arn == null ? [] : [var.kms_key_arn]

    content {
      sid       = "DecryptBeaconKey"
      actions   = ["kms:Decrypt"]
      resources = [statement.value]
    }
  }
}

# Shared-secret access — directive Lambda only (the OAuth proxy never signs).
data "aws_iam_policy_document" "directive_lambda_access" {
  source_policy_documents = [data.aws_iam_policy_document.beacon_read.json]

  statement {
    sid       = "ReadSharedSecretParameter"
    actions   = ["ssm:GetParameter"]
    resources = [var.shared_secret_parameter_arn]
  }
}

# ── Directive Lambda role ────────────────────────────────────────────────────
resource "aws_iam_role" "directive_lambda" {
  name               = "${var.name_prefix}-directive-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "directive_lambda" {
  name   = "${var.name_prefix}-directive-lambda-access"
  role   = aws_iam_role.directive_lambda.id
  policy = data.aws_iam_policy_document.directive_lambda_access.json
}

resource "aws_iam_role_policy_attachment" "directive_lambda_logs" {
  role       = aws_iam_role.directive_lambda.name
  policy_arn = local.lambda_basic_execution_arn
}

# ── OAuth proxy Lambda role ──────────────────────────────────────────────────
resource "aws_iam_role" "oauth_lambda" {
  name               = "${var.name_prefix}-oauth-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "oauth_lambda" {
  name   = "${var.name_prefix}-oauth-lambda-access"
  role   = aws_iam_role.oauth_lambda.id
  policy = data.aws_iam_policy_document.beacon_read.json
}

resource "aws_iam_role_policy_attachment" "oauth_lambda_logs" {
  role       = aws_iam_role.oauth_lambda.name
  policy_arn = local.lambda_basic_execution_arn
}

# ── Home server beacon publisher ─────────────────────────────────────────────
data "aws_iam_policy_document" "home_publisher" {
  statement {
    sid       = "WriteBeaconObject"
    actions   = ["s3:PutObject"]
    resources = [var.beacon_object_arn]
  }

  # SSE-KMS: writing the beacon object requires a data key from the bucket key.
  dynamic "statement" {
    for_each = var.kms_key_arn == null ? [] : [var.kms_key_arn]

    content {
      sid       = "UseBeaconKey"
      actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_user" "home_publisher" {
  count = var.create_home_publisher_user ? 1 : 0

  name = "${var.name_prefix}-home-publisher"
}

resource "aws_iam_user_policy" "home_publisher" {
  count = var.create_home_publisher_user ? 1 : 0

  name   = "${var.name_prefix}-home-publisher-access"
  user   = aws_iam_user.home_publisher[0].name
  policy = data.aws_iam_policy_document.home_publisher.json
}
