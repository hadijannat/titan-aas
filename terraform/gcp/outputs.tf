# Titan-AAS GCP Terraform Outputs

# ============================================
# VPC
# ============================================
output "vpc_id" {
  description = "VPC network ID"
  value       = google_compute_network.vpc.id
}

output "vpc_name" {
  description = "VPC network name"
  value       = google_compute_network.vpc.name
}

output "subnet_id" {
  description = "Private subnet ID"
  value       = google_compute_subnetwork.private.id
}

# ============================================
# GKE
# ============================================
output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.primary.name
}

output "cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.primary.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "GKE cluster CA certificate"
  value       = google_container_cluster.primary.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${var.gcp_region} --project ${var.gcp_project}"
}

# ============================================
# Cloud SQL
# ============================================
output "database_private_ip" {
  description = "Cloud SQL private IP address"
  value       = google_sql_database_instance.main.private_ip_address
}

output "database_connection_name" {
  description = "Cloud SQL connection name"
  value       = google_sql_database_instance.main.connection_name
}

output "database_password_secret" {
  description = "Secret Manager secret ID for database password"
  value       = google_secret_manager_secret.db_password.secret_id
}

# ============================================
# Memorystore Redis
# ============================================
output "redis_host" {
  description = "Memorystore Redis host"
  value       = google_redis_instance.main.host
}

output "redis_port" {
  description = "Memorystore Redis port"
  value       = google_redis_instance.main.port
}

output "redis_auth_secret" {
  description = "Secret Manager secret ID for Redis auth string"
  value       = google_secret_manager_secret.redis_auth.secret_id
}

# ============================================
# Cloud Storage
# ============================================
output "storage_bucket_name" {
  description = "Cloud Storage bucket name"
  value       = google_storage_bucket.blobs.name
}

output "storage_bucket_url" {
  description = "Cloud Storage bucket URL"
  value       = google_storage_bucket.blobs.url
}

# ============================================
# Workload Identity
# ============================================
output "titan_service_account_email" {
  description = "GCP service account email for Titan-AAS pods"
  value       = google_service_account.titan_aas.email
}

# ============================================
# Ingress
# ============================================
output "ingress_ip" {
  description = "Static IP address for ingress"
  value       = google_compute_global_address.ingress.address
}

output "application_url" {
  description = "URL for the Titan-AAS application"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${google_compute_global_address.ingress.address}"
}
