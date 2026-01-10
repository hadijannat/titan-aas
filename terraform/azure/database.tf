# Titan-AAS Azure PostgreSQL Flexible Server

# ============================================
# Delegated Subnet for PostgreSQL
# ============================================
resource "azurerm_subnet" "postgresql" {
  name                 = "postgresql-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.postgresql_subnet_cidr]

  delegation {
    name = "postgresql-delegation"
    service_delegation {
      name = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action"
      ]
    }
  }
}

# ============================================
# Private DNS Zone for PostgreSQL
# ============================================
resource "azurerm_private_dns_zone" "postgresql" {
  name                = "${var.project_name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name

  tags = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgresql" {
  name                  = "postgresql-vnet-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.postgresql.name
  virtual_network_id    = azurerm_virtual_network.main.id
}

# ============================================
# PostgreSQL Flexible Server
# ============================================
resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "${var.project_name}-db"
  location               = azurerm_resource_group.main.location
  resource_group_name    = azurerm_resource_group.main.name
  version                = "16"
  delegated_subnet_id    = azurerm_subnet.postgresql.id
  private_dns_zone_id    = azurerm_private_dns_zone.postgresql.id
  administrator_login    = "titan"
  administrator_password = random_password.db_password.result
  zone                   = var.environment == "production" ? "1" : null

  # Compute tier
  sku_name = var.db_sku_name

  # Storage
  storage_mb = var.db_storage_mb

  # High availability
  dynamic "high_availability" {
    for_each = var.environment == "production" ? [1] : []
    content {
      mode                      = "ZoneRedundant"
      standby_availability_zone = "2"
    }
  }

  # Backup
  backup_retention_days        = var.environment == "production" ? 35 : 7
  geo_redundant_backup_enabled = var.environment == "production"

  # Maintenance window
  maintenance_window {
    day_of_week  = 0 # Sunday
    start_hour   = 4
    start_minute = 0
  }

  tags = local.common_tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgresql]
}

# ============================================
# Database
# ============================================
resource "azurerm_postgresql_flexible_server_database" "titan" {
  name      = "titan"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "utf8"
  collation = "en_US.utf8"
}

# ============================================
# Server Configuration
# ============================================
resource "azurerm_postgresql_flexible_server_configuration" "log_statement" {
  name      = "log_statement"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "all"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_min_duration" {
  name      = "log_min_duration_statement"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "1000"
}

# ============================================
# Key Vault for Secrets
# ============================================
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                       = "${replace(var.project_name, "-", "")}kv${substr(md5(azurerm_resource_group.main.id), 0, 6)}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = var.environment == "production"
  soft_delete_retention_days = 7

  enable_rbac_authorization = true

  network_acls {
    bypass         = "AzureServices"
    default_action = "Allow"
  }

  tags = local.common_tags
}

# ============================================
# Store Password in Key Vault
# ============================================
resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "db_password" {
  name         = "titan-db-password"
  value        = random_password.db_password.result
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.kv_admin]
}
