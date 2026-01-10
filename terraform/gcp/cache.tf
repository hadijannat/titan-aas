# Titan-AAS GCP Memorystore Redis

# ============================================
# Memorystore Redis Instance
# ============================================
resource "google_redis_instance" "main" {
  name               = "${var.project_name}-redis"
  tier               = var.environment == "production" ? "STANDARD_HA" : "BASIC"
  memory_size_gb     = var.redis_memory_size_gb
  region             = var.gcp_region
  project            = var.gcp_project
  authorized_network = google_compute_network.vpc.id

  redis_version = "REDIS_7_0"
  display_name  = "Titan-AAS Redis"

  # In-transit encryption
  transit_encryption_mode = "SERVER_AUTHENTICATION"
  auth_enabled            = true

  # Connect mode for private access
  connect_mode = "PRIVATE_SERVICE_ACCESS"

  # Maintenance window
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 4
        minutes = 0
      }
    }
  }

  # Redis configs
  redis_configs = {
    maxmemory-policy = "volatile-lru"
  }

  labels = {
    project     = var.project_name
    environment = var.environment
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# ============================================
# Store Redis Auth String in Secret Manager
# ============================================
resource "google_secret_manager_secret" "redis_auth" {
  secret_id = "${var.project_name}-redis-auth"
  project   = var.gcp_project

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "redis_auth" {
  secret      = google_secret_manager_secret.redis_auth.id
  secret_data = google_redis_instance.main.auth_string
}
