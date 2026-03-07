# ============================================================
# VPC Module — Network Infrastructure
# 
# Creates an isolated network with:
# - Public subnets (for load balancers)
# - Private subnets (for pods — not directly internet accessible)
# - NAT gateway (lets private subnets reach the internet)
#
# We use the community module because VPC setup involves
# dozens of resources (subnets, route tables, internet
# gateways, NAT gateways, etc.). The module handles it all.
# ============================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = var.vpc_name
  cidr = var.vpc_cidr

  # Deploy across multiple availability zones
  # This gives high availability — if one AZ goes down,
  # the other keeps running
  azs             = var.availability_zones
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs

  # NAT Gateway — lets pods in private subnets access
  # the internet (to pull Docker images, call APIs, etc.)
  # but the internet can't reach them directly
  # single_nat_gateway = true saves cost in dev
  # In production, set to false for one NAT per AZ
  enable_nat_gateway   = true
  single_nat_gateway   = var.single_nat_gateway
  enable_dns_hostnames = true

  # Tags that EKS requires to auto-discover subnets
  # Without these, the load balancer can't find where to deploy
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }

  tags = var.tags
}