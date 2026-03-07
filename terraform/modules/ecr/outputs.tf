# ============================================================
# ECR Module Outputs
# 
# These are values other modules can reference.
# Like a Python function's return values.
# The EKS module needs the repository URL to pull images.
# ============================================================

output "repository_url" {
  description = "The URL of the ECR repository"
  value       = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  description = "The ARN of the ECR repository"
  value       = aws_ecr_repository.this.arn
}