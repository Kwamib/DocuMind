# ============================================================
# ECR Module Variables
# 
# These are the inputs this module accepts.
# The root module (terraform/main.tf) passes values in.
# Think of it like function parameters in Python.
# ============================================================

variable "repository_name" {
  description = "Name of the ECR repository"
  type        = string
}

variable "max_image_count" {
  description = "Maximum number of images to keep"
  type        = number
  default     = 10
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}