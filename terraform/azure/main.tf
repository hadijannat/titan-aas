# Titan-AAS Azure Infrastructure
# Resource Group, VNet, AKS Cluster

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ============================================
# Resource Group
# ============================================
resource "azurerm_resource_group" "main" {
  name     = "${var.project_name}-${var.environment}-rg"
  location = var.azure_region

  tags = local.common_tags
}

# ============================================
# Virtual Network
# ============================================
resource "azurerm_virtual_network" "main" {
  name                = "${var.project_name}-vnet"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.vnet_cidr]

  tags = local.common_tags
}

# ============================================
# Subnets
# ============================================
resource "azurerm_subnet" "aks" {
  name                 = "aks-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.aks_subnet_cidr]
}

resource "azurerm_subnet" "private_endpoints" {
  name                 = "private-endpoints"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.private_endpoints_subnet_cidr]
}

# ============================================
# NAT Gateway
# ============================================
resource "azurerm_public_ip" "nat" {
  name                = "${var.project_name}-nat-ip"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  zones               = var.environment == "production" ? ["1", "2", "3"] : []

  tags = local.common_tags
}

resource "azurerm_nat_gateway" "main" {
  name                    = "${var.project_name}-nat"
  location                = azurerm_resource_group.main.location
  resource_group_name     = azurerm_resource_group.main.name
  sku_name                = "Standard"
  idle_timeout_in_minutes = 10
  zones                   = var.environment == "production" ? ["1"] : []

  tags = local.common_tags
}

resource "azurerm_nat_gateway_public_ip_association" "main" {
  nat_gateway_id       = azurerm_nat_gateway.main.id
  public_ip_address_id = azurerm_public_ip.nat.id
}

resource "azurerm_subnet_nat_gateway_association" "aks" {
  subnet_id      = azurerm_subnet.aks.id
  nat_gateway_id = azurerm_nat_gateway.main.id
}

# ============================================
# Log Analytics Workspace
# ============================================
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.project_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = local.common_tags
}

# ============================================
# User-Assigned Managed Identity for AKS
# ============================================
resource "azurerm_user_assigned_identity" "aks" {
  name                = "${var.project_name}-aks-identity"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  tags = local.common_tags
}

# ============================================
# AKS Cluster
# ============================================
resource "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.kubernetes_version

  # System node pool
  default_node_pool {
    name                = "system"
    node_count          = var.node_desired_size
    vm_size             = var.node_vm_size
    vnet_subnet_id      = azurerm_subnet.aks.id
    min_count           = var.node_min_size
    max_count           = var.node_max_size
    enable_auto_scaling = true
    os_disk_size_gb     = 100
    os_disk_type        = "Managed"

    # Availability zones for HA
    zones = var.environment == "production" ? ["1", "2", "3"] : []

    node_labels = {
      "role" = "system"
    }

    tags = local.common_tags
  }

  # Use user-assigned identity
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks.id]
  }

  # Enable Workload Identity
  workload_identity_enabled = true
  oidc_issuer_enabled       = true

  # Network configuration
  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    load_balancer_sku = "standard"
    outbound_type     = "userAssignedNATGateway"
  }

  # Azure Policy
  azure_policy_enabled = true

  # Key Vault secrets provider
  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  # Microsoft Defender
  microsoft_defender {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  # OMS Agent for monitoring
  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  # Automatic upgrades
  automatic_channel_upgrade = var.environment == "production" ? "stable" : "rapid"

  # Maintenance window
  maintenance_window {
    allowed {
      day   = "Sunday"
      hours = [4, 5, 6, 7]
    }
  }

  tags = local.common_tags

  depends_on = [azurerm_subnet_nat_gateway_association.aks]
}

# ============================================
# Application Node Pool
# ============================================
resource "azurerm_kubernetes_cluster_node_pool" "main" {
  name                  = "main"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.node_vm_size
  node_count            = var.node_desired_size
  vnet_subnet_id        = azurerm_subnet.aks.id
  min_count             = var.node_min_size
  max_count             = var.node_max_size
  enable_auto_scaling   = true
  os_disk_size_gb       = 100
  os_disk_type          = "Managed"

  zones = var.environment == "production" ? ["1", "2", "3"] : []

  node_labels = {
    "role" = "main"
  }

  tags = local.common_tags
}

# ============================================
# Role Assignments for AKS Identity
# ============================================
resource "azurerm_role_assignment" "aks_network_contributor" {
  scope                = azurerm_virtual_network.main.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.aks.principal_id
}
