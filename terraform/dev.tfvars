# ============================================================
# Dev Environment Configuration
# 
# Use with: terraform apply -var-file=environments/dev.tfvars
# 
# This keeps environment-specific values separate from
# the infrastructure code. For production, create a
# prod.tfvars with different values.
# ============================================================

aws_region = "us-east-1"

common_tags = {
  Project     = "DocuMind"
  Environment = "dev"
  ManagedBy   = "terraform"
}