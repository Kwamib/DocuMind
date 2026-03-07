# ============================================================
# EKS Module — Kubernetes Cluster
# 
# Creates a managed Kubernetes cluster on AWS.
# AWS handles the control plane (API server, etcd, scheduler).
# You manage the worker nodes via managed node groups.
#
# The community module simplifies what would otherwise be
# 200+ lines of IAM roles, security groups, and configs.
# ============================================================

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  # Network configuration — which VPC and subnets to use
  # Passed in from the VPC module's outputs
  vpc_id     = var.vpc_id
  subnet_ids = var.subnet_ids

  # Allow kubectl access from outside the VPC
  # In production, you might restrict this to specific IPs
  cluster_endpoint_public_access = true

  # Managed node group — the EC2 instances running your pods
  eks_managed_node_groups = {
    documind_nodes = {
      desired_size = var.node_desired_size
      min_size     = var.node_min_size
      max_size     = var.node_max_size

      instance_types = var.node_instance_types
      ami_type       = "AL2_x86_64"
    }
  }

  tags = var.tags
}