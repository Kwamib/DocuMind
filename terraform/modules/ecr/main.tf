# ============================================================
# ECR Module — Container Registry
# 
# This module creates an ECR repository where your
# Docker images are stored. It's isolated so you could
# reuse it for other projects by changing the name.
# ============================================================

resource "aws_ecr_repository" "this" {
  # "this" is a common convention in modules
  # It means "the main resource this module manages"
  name                 = var.repository_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last ${var.max_image_count} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.max_image_count
      }
      action = {
        type = "expire"
      }
    }]
  })
}