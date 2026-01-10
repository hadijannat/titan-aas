# Titan-AAS GCP Cloud SQL PostgreSQL

# ============================================
# Private Services Access for Cloud SQL
# ============================================
resource "google_compute_global_address" "private_ip_range" {
  name          = "${var.project_name}-private-ip-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
  project       = var.gcp_project
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]
}

# ============================================
# Cloud SQL PostgreSQL Instance
# ============================================
resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "main" {
  name             = "${var.project_name}-db"
  database_version = "POSTGRES_16"
  region           = var.gcp_region
  project          = var.gcp_project

  depends_on = [google_service_networking_connection.private_vpc_connection]

  settings {
    tier              = var.db_tier
    availability_type = var.environment == "production" ? "REGIONAL" : "ZONAL"
    disk_size         = var.db_disk_size
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = var.environment == "production"
      backup_retention_settings {
        retained_backups = var.environment == "production" ? 30 : 7
      }
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }

    maintenance_window {
      day  = 7 # Sunday
      hour = 4
    }

    database_flags {
      name  = "log_statement"
      value = "all"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }
  }

  deletion_protection = var.environment == "production"
}

# ============================================
# Database and User
# ============================================
resource "google_sql_database" "titan" {
  name     = "titan"
  instance = google_sql_database_instance.main.name
  project  = var.gcp_project
}

resource "google_sql_user" "titan" {
  name     = "titan"
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
  project  = var.gcp_project
}

# ============================================
# Store Password in Secret Manager
# ============================================
resource "google_secret_manager_secret" "db_password" {
  secret_id = "${var.project_name}-db-password"
  project   = var.gcp_project

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}
