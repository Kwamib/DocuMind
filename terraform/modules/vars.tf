# ============================================================
# Root Variables
# 
# These are the top-level inputs for the entire deployment.
# Override with terraform.tfvars or -var flag.
# ============================================================

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "common_tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default = {
    Project     = "DocuMind"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}