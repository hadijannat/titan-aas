# Titan-AAS GCP Infrastructure
# VPC, GKE Cluster, and Networking

# ============================================
# VPC Network
# ============================================
resource "google_compute_network" "vpc" {
  name                    = "${var.project_name}-vpc"
  auto_create_subnetworks = false
  project                 = var.gcp_project
}

resource "google_compute_subnetwork" "private" {
  name          = "${var.project_name}-private"
  ip_cidr_range = var.private_subnet_cidr
  region        = var.gcp_region
  network       = google_compute_network.vpc.id
  project       = var.gcp_project

  # Secondary ranges for GKE pods and services
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }

  private_ip_google_access = true
}

# ============================================
# Cloud Router and NAT
# ============================================
resource "google_compute_router" "router" {
  name    = "${var.project_name}-router"
  region  = var.gcp_region
  network = google_compute_network.vpc.id
  project = var.gcp_project
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.project_name}-nat"
  router                             = google_compute_router.router.name
  region                             = var.gcp_region
  project                            = var.gcp_project
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# ============================================
# Firewall Rules
# ============================================
resource "google_compute_firewall" "allow_internal" {
  name    = "${var.project_name}-allow-internal"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {
    protocol = "icmp"
  }

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  source_ranges = [
    var.private_subnet_cidr,
    var.pods_cidr,
    var.services_cidr,
  ]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "${var.project_name}-allow-health-checks"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {
    protocol = "tcp"
  }

  # Google Cloud health check ranges
  source_ranges = [
    "35.191.0.0/16",
    "130.211.0.0/22",
  ]

  target_tags = ["gke-node"]
}

# ============================================
# GKE Cluster
# ============================================
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.gcp_region
  project  = var.gcp_project

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.private.name

  # VPC-native cluster
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Enable Workload Identity
  workload_identity_config {
    workload_pool = "${var.gcp_project}.svc.id.goog"
  }

  # Private cluster
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }

  # Master authorized networks
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "0.0.0.0/0"
      display_name = "All"
    }
  }

  # Addons
  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
  }

  # Release channel
  release_channel {
    channel = var.environment == "production" ? "STABLE" : "REGULAR"
  }

  # Maintenance window
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-01T04:00:00Z"
      end_time   = "2024-01-01T08:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
  }

  # Logging and monitoring
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }

  # Binary authorization (optional)
  binary_authorization {
    evaluation_mode = var.environment == "production" ? "PROJECT_SINGLETON_POLICY_ENFORCE" : "DISABLED"
  }

  # Network policy
  network_policy {
    enabled  = true
    provider = "CALICO"
  }

  # Dataplane V2 for improved networking
  datapath_provider = "ADVANCED_DATAPATH"

  lifecycle {
    ignore_changes = [
      node_config,
    ]
  }
}

# ============================================
# Node Pool
# ============================================
resource "google_service_account" "gke_nodes" {
  account_id   = "${var.project_name}-gke-nodes"
  display_name = "GKE Node Service Account"
  project      = var.gcp_project
}

resource "google_project_iam_member" "gke_nodes_log_writer" {
  project = var.gcp_project
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_metric_writer" {
  project = var.gcp_project
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.gcp_project
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_artifact_reader" {
  project = var.gcp_project
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_container_node_pool" "main" {
  name       = "main"
  location   = var.gcp_region
  cluster    = google_container_cluster.primary.name
  project    = var.gcp_project
  node_count = var.node_desired_size

  autoscaling {
    min_node_count = var.node_min_size
    max_node_count = var.node_max_size
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = 100
    disk_type    = "pd-standard"

    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Enable Workload Identity on nodes
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = {
      role = "main"
    }

    tags = ["gke-node", var.project_name]

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  lifecycle {
    ignore_changes = [
      node_count,
    ]
  }
}

# ============================================
# Static IP for Ingress
# ============================================
resource "google_compute_global_address" "ingress" {
  name    = "${var.project_name}-ingress-ip"
  project = var.gcp_project
}

# ============================================
# Managed SSL Certificate
# ============================================
resource "google_compute_managed_ssl_certificate" "titan" {
  count   = var.domain_name != "" ? 1 : 0
  name    = "${var.project_name}-cert"
  project = var.gcp_project

  managed {
    domains = [var.domain_name]
  }
}
