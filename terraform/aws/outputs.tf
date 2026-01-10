# Titan-AAS AWS Terraform Outputs

# ============================================
# VPC
# ============================================
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnets" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}

output "public_subnets" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnets
}

# ============================================
# EKS
# ============================================
output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data for the cluster"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

# ============================================
# RDS
# ============================================
output "rds_endpoint" {
  description = "RDS endpoint"
  value       = module.rds.db_instance_address
}

output "rds_port" {
  description = "RDS port"
  value       = module.rds.db_instance_port
}

output "rds_master_user_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the master password"
  value       = module.rds.db_instance_master_user_secret_arn
}

# ============================================
# ElastiCache
# ============================================
output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = module.elasticache.replication_group_primary_endpoint_address
}

output "redis_port" {
  description = "Redis port"
  value       = 6379
}

# ============================================
# S3
# ============================================
output "s3_bucket_name" {
  description = "S3 bucket name for blobs"
  value       = module.s3_bucket.s3_bucket_id
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = module.s3_bucket.s3_bucket_arn
}

# ============================================
# Application
# ============================================
output "titan_service_account_role_arn" {
  description = "IAM role ARN for Titan-AAS service account"
  value       = module.s3_irsa.iam_role_arn
}

output "application_url" {
  description = "URL for the Titan-AAS application"
  value       = "https://${var.domain_name}"
}

# ============================================
# Monitoring
# ============================================
output "cloudwatch_log_group" {
  description = "CloudWatch log group for the cluster"
  value       = "/aws/eks/${var.cluster_name}/cluster"
}
