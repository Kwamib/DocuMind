# ============================================================
# DocuMind — Root Terraform Configuration
# 
# This is the "main" file that uses all three modules.
# Think of it like main.py — it imports and connects
# the individual modules together.
#
# Each module is like a function:
#   module "ecr" = create_ecr_repository(name="documind")
#   module "vpc" = create_vpc(name="documind-vpc", ...)
#   module "eks" = create_eks_cluster(vpc=vpc, ...)
#
# Modules reference each other through outputs:
#   module.vpc.vpc_id gets passed to module.eks.vpc_id
# ============================================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ============================================================
# Module 1: ECR — Where Docker images are stored
# ============================================================
module "ecr" {
  source = "./modules/ecr"

  repository_name = "documind"
  max_image_count = 10
  tags            = var.common_tags
}

# ============================================================
# Module 2: VPC — Network infrastructure
# 
# This creates the isolated network that EKS runs inside.
# We pass in the region to construct availability zone names.
# ============================================================
module "vpc" {
  source = "./modules/vpc"

  vpc_name           = "documind-vpc"
  vpc_cidr           = "10.0.0.0/16"
  availability_zones = ["${var.aws_region}a", "${var.aws_region}b"]
  single_nat_gateway = true    # Save cost in dev
  tags               = var.common_tags
}

# ============================================================
# Module 3: EKS — Kubernetes cluster
# 
# This creates the cluster. Notice how it references
# outputs from the VPC module:
#   vpc_id     = module.vpc.vpc_id
#   subnet_ids = module.vpc.private_subnet_ids
#
# Terraform understands this dependency and creates
# the VPC first, then the EKS cluster.
# ============================================================
module "eks" {
  source = "./modules/eks"

  cluster_name   = "documind-cluster"
  vpc_id         = module.vpc.vpc_id
  subnet_ids     = module.vpc.private_subnet_ids
  
  node_desired_size   = 2
  node_min_size       = 1
  node_max_size       = 3
  node_instance_types = ["t3.medium"]
  
  tags = var.common_tags
}