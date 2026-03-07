# ============================================================
# Production Environment Configuration
# 
# Use with: terraform apply -var-file=environments/prod.tfvars
# ============================================================

aws_region = "us-east-1"

common_tags = {
  Project     = "DocuMind"
  Environment = "prod"
  ManagedBy   = "terraform"
}