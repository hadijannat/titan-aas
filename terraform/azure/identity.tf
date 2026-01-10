# Titan-AAS Azure Workload Identity

# ============================================
# User-Assigned Managed Identity for Titan-AAS
# ============================================
resource "azurerm_user_assigned_identity" "titan" {
  name                = "${var.project_name}-identity"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  tags = local.common_tags
}

# ============================================
# Federated Identity Credential for Workload Identity
# ============================================
resource "azurerm_federated_identity_credential" "titan" {
  name                = "${var.project_name}-federated-credential"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.titan.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:${var.kubernetes_namespace}:${var.project_name}"
}

# ============================================
# Role Assignments for Titan-AAS Identity
# ============================================

# Key Vault Secrets User - read secrets
resource "azurerm_role_assignment" "titan_kv_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.titan.principal_id
}

# Storage Blob Data Contributor - read/write AASX files
resource "azurerm_role_assignment" "titan_storage" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.titan.principal_id
}

# Monitoring Metrics Publisher - push metrics
resource "azurerm_role_assignment" "titan_monitoring" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_user_assigned_identity.titan.principal_id
}

# ============================================
# AKS Kubelet Identity Role Assignments
# ============================================

# Allow AKS to pull images from ACR if using one
# resource "azurerm_role_assignment" "aks_acr" {
#   scope                = azurerm_container_registry.main.id
#   role_definition_name = "AcrPull"
#   principal_id         = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
# }

# Allow AKS identity to manage networking
resource "azurerm_role_assignment" "aks_subnet" {
  scope                = azurerm_subnet.aks.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
}
