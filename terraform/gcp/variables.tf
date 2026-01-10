# Titan-AAS GCP Terraform Variables

# ============================================
# General
# ============================================
variable "gcp_project" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "titan-aas"
}

variable "environment" {
  description = "Environment (development, staging, production)"
  type        = string
  default     = "development"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be one of: development, staging, production."
  }
}

# ============================================
# Networking
# ============================================
variable "private_subnet_cidr" {
  description = "CIDR for private subnet"
  type        = string
  default     = "10.0.0.0/20"
}

variable "pods_cidr" {
  description = "Secondary CIDR for GKE pods"
  type        = string
  default     = "10.4.0.0/14"
}

variable "services_cidr" {
  description = "Secondary CIDR for GKE services"
  type        = string
  default     = "10.8.0.0/20"
}

variable "master_cidr" {
  description = "CIDR for GKE master nodes (must be /28)"
  type        = string
  default     = "172.16.0.0/28"
}

# ============================================
# GKE
# ============================================
variable "cluster_name" {
  description = "GKE cluster name"
  type        = string
  default     = "titan-aas-cluster"
}

variable "kubernetes_version" {
  description = "Kubernetes version (empty for default)"
  type        = string
  default     = ""
}

variable "node_machine_type" {
  description = "Machine type for GKE nodes"
  type        = string
  default     = "e2-standard-4"
}

variable "node_min_size" {
  description = "Minimum nodes in pool"
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum nodes in pool"
  type        = number
  default     = 10
}

variable "node_desired_size" {
  description = "Desired nodes in pool"
  type        = number
  default     = 3
}

# ============================================
# Cloud SQL
# ============================================
variable "db_tier" {
  description = "Cloud SQL machine tier (e.g., db-custom-2-8192 = 2 vCPU, 8GB RAM)"
  type        = string
  default     = "db-custom-2-8192"
}

variable "db_disk_size" {
  description = "Database disk size in GB"
  type        = number
  default     = 20
}

# ============================================
# Memorystore Redis
# ============================================
variable "redis_memory_size_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 1
}

# ============================================
# Application
# ============================================
variable "titan_image_repository" {
  description = "Docker image repository for Titan-AAS"
  type        = string
  default     = "ghcr.io/your-org/titan-aas"
}

variable "titan_image_tag" {
  description = "Docker image tag for Titan-AAS"
  type        = string
  default     = "latest"
}

variable "domain_name" {
  description = "Domain name for the application (leave empty to skip ingress TLS)"
  type        = string
  default     = ""
}
