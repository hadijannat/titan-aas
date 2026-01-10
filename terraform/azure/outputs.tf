# Titan-AAS Azure Terraform Outputs

# ============================================
# Resource Group
# ============================================
output "resource_group_name" {
  description = "Name of the Azure Resource Group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "Location of the Azure Resource Group"
  value       = azurerm_resource_group.main.location
}

# ============================================
# Networking
# ============================================
output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Name of the Virtual Network"
  value       = azurerm_virtual_network.main.name
}

output "aks_subnet_id" {
  description = "ID of the AKS subnet"
  value       = azurerm_subnet.aks.id
}

output "nat_gateway_public_ip" {
  description = "Public IP address of the NAT Gateway"
  value       = azurerm_public_ip.nat.ip_address
}

# ============================================
# AKS
# ============================================
output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.name
}

output "aks_cluster_id" {
  description = "ID of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.id
}

output "aks_cluster_fqdn" {
  description = "FQDN of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.fqdn
}

output "aks_oidc_issuer_url" {
  description = "OIDC issuer URL for Workload Identity"
  value       = azurerm_kubernetes_cluster.main.oidc_issuer_url
}

output "aks_get_credentials_command" {
  description = "Azure CLI command to get AKS credentials"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${azurerm_kubernetes_cluster.main.name}"
}

# ============================================
# PostgreSQL
# ============================================
output "postgresql_server_name" {
  description = "Name of the PostgreSQL Flexible Server"
  value       = azurerm_postgresql_flexible_server.main.name
}

output "postgresql_server_fqdn" {
  description = "FQDN of the PostgreSQL Flexible Server"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgresql_database_name" {
  description = "Name of the PostgreSQL database"
  value       = azurerm_postgresql_flexible_server_database.titan.name
}

output "postgresql_admin_username" {
  description = "Administrator username for PostgreSQL"
  value       = azurerm_postgresql_flexible_server.main.administrator_login
  sensitive   = true
}

# ============================================
# Redis
# ============================================
output "redis_cache_name" {
  description = "Name of the Azure Cache for Redis"
  value       = azurerm_redis_cache.main.name
}

output "redis_cache_hostname" {
  description = "Hostname of the Azure Cache for Redis"
  value       = azurerm_redis_cache.main.hostname
}

output "redis_cache_ssl_port" {
  description = "SSL port of the Azure Cache for Redis"
  value       = azurerm_redis_cache.main.ssl_port
}

output "redis_cache_private_ip" {
  description = "Private IP address of the Redis private endpoint"
  value       = azurerm_private_endpoint.redis.private_service_connection[0].private_ip_address
}

# ============================================
# Storage
# ============================================
output "storage_account_name" {
  description = "Name of the Storage Account"
  value       = azurerm_storage_account.main.name
}

output "storage_account_primary_endpoint" {
  description = "Primary blob endpoint of the Storage Account"
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "storage_container_name" {
  description = "Name of the blob container for AASX files"
  value       = azurerm_storage_container.aasx.name
}

# ============================================
# Key Vault
# ============================================
output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

# ============================================
# Workload Identity
# ============================================
output "titan_identity_client_id" {
  description = "Client ID of the Titan-AAS managed identity"
  value       = azurerm_user_assigned_identity.titan.client_id
}

output "titan_identity_principal_id" {
  description = "Principal ID of the Titan-AAS managed identity"
  value       = azurerm_user_assigned_identity.titan.principal_id
}

# ============================================
# Helm
# ============================================
output "helm_release_name" {
  description = "Name of the Helm release"
  value       = helm_release.titan.name
}

output "helm_release_namespace" {
  description = "Namespace of the Helm release"
  value       = helm_release.titan.namespace
}

output "helm_release_version" {
  description = "Version of the Helm release"
  value       = helm_release.titan.version
}

# ============================================
# Application Access
# ============================================
output "application_url" {
  description = "URL to access the Titan-AAS application"
  value       = "https://${var.domain_name}"
}
