output "bucket_name" {
  description = "Name of the beacon bucket."
  value       = aws_s3_bucket.beacon.bucket
}

output "bucket_arn" {
  description = "ARN of the beacon bucket."
  value       = aws_s3_bucket.beacon.arn
}

output "beacon_object_key" {
  description = "Object key of the beacon document."
  value       = var.beacon_object_key
}

output "beacon_object_arn" {
  description = "ARN of the single beacon object (least-privilege IAM)."
  value       = "${aws_s3_bucket.beacon.arn}/${var.beacon_object_key}"
}
