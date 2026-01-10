# Titan-AAS Azure Terraform Variables

# ============================================
# General
# ============================================
variable "azure_region" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "titan-aas"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}[a-z0-9]$", var.project_name))
    error_message = "Project name must be 3-22 lowercase alphanumeric characters, starting with a letter."
  }
}

variable "environment" {
  description = "Environment (development, staging, production)"
  type        = string
  default     = "development"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

# ============================================
# Networking
# ============================================
variable "vnet_cidr" {
  description = "CIDR block for VNet"
  type        = string
  default     = "10.0.0.0/16"
}

variable "aks_subnet_cidr" {
  description = "CIDR block for AKS subnet"
  type        = string
  default     = "10.0.0.0/20"
}

variable "postgresql_subnet_cidr" {
  description = "CIDR block for PostgreSQL delegated subnet"
  type        = string
  default     = "10.0.16.0/24"
}

variable "private_endpoints_subnet_cidr" {
  description = "CIDR block for private endpoints subnet"
  type        = string
  default     = "10.0.17.0/24"
}

# ============================================
# AKS
# ============================================
variable "cluster_name" {
  description = "Name of the AKS cluster"
  type        = string
  default     = "titan-aas-cluster"
}

variable "kubernetes_version" {
  description = "Kubernetes version for AKS"
  type        = string
  default     = "1.29"
}

variable "node_vm_size" {
  description = "VM size for AKS nodes"
  type        = string
  default     = "Standard_D4s_v3"
}

variable "node_min_size" {
  description = "Minimum number of nodes in the node pool"
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum number of nodes in the node pool"
  type        = number
  default     = 10
}

variable "node_desired_size" {
  description = "Desired number of nodes in the node pool"
  type        = number
  default     = 3
}

# ============================================
# PostgreSQL
# ============================================
variable "db_sku_name" {
  description = "SKU for PostgreSQL Flexible Server"
  type        = string
  default     = "GP_Standard_D4s_v3"
}

variable "db_storage_mb" {
  description = "Storage size for PostgreSQL in MB"
  type        = number
  default     = 65536 # 64GB

  validation {
    condition     = var.db_storage_mb >= 32768
    error_message = "Database storage must be at least 32GB (32768 MB)."
  }
}

# ============================================
# Redis
# ============================================
variable "redis_capacity" {
  description = "Redis cache capacity (size of the cache)"
  type        = number
  default     = 1

  validation {
    condition     = contains([1, 2, 3, 4], var.redis_capacity)
    error_message = "Redis capacity for Premium tier must be 1, 2, 3, or 4."
  }
}

variable "redis_family" {
  description = "Redis cache family"
  type        = string
  default     = "P"

  validation {
    condition     = contains(["P"], var.redis_family)
    error_message = "Redis family must be P (Premium) for private endpoint support."
  }
}

variable "redis_sku_name" {
  description = "Redis cache SKU (Premium required for private endpoint)"
  type        = string
  default     = "Premium"

  validation {
    condition     = var.redis_sku_name == "Premium"
    error_message = "Redis SKU must be Premium for private endpoint support."
  }
}

# ============================================
# Application
# ============================================
variable "titan_image_repository" {
  description = "Container image repository for Titan-AAS"
  type        = string
  default     = "ghcr.io/your-org/titan-aas"
}

variable "titan_image_tag" {
  description = "Container image tag for Titan-AAS"
  type        = string
  default     = "latest"
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "aas.example.com"
}

# ============================================
# Kubernetes / Helm
# ============================================
variable "kubernetes_namespace" {
  description = "Kubernetes namespace for Titan-AAS"
  type        = string
  default     = "titan"
}

variable "helm_chart_path" {
  description = "Path to the Helm chart"
  type        = string
  default     = "../../charts/titan-aas"
}

variable "helm_chart_version" {
  description = "Version of the Helm chart"
  type        = string
  default     = "0.1.0"
}

variable "install_nginx_ingress" {
  description = "Install NGINX Ingress Controller"
  type        = bool
  default     = true
}

variable "install_cert_manager" {
  description = "Install cert-manager for TLS certificates"
  type        = bool
  default     = true
}
