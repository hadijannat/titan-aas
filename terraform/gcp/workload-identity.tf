# Titan-AAS GCP Workload Identity

# ============================================
# GCP Service Account for Titan-AAS Pods
# ============================================
resource "google_service_account" "titan_aas" {
  account_id   = "titan-aas"
  display_name = "Titan-AAS Workload Identity"
  description  = "Service account for Titan-AAS pods via Workload Identity"
  project      = var.gcp_project
}

# ============================================
# Workload Identity Binding
# ============================================
# Allow Kubernetes service account to impersonate GCP service account
resource "google_service_account_iam_member" "titan_workload_identity" {
  service_account_id = google_service_account.titan_aas.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.gcp_project}.svc.id.goog[titan/titan-aas]"
}

# ============================================
# Secret Manager Access
# ============================================
resource "google_secret_manager_secret_iam_member" "titan_db_password" {
  secret_id = google_secret_manager_secret.db_password.secret_id
  project   = var.gcp_project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.titan_aas.email}"
}

resource "google_secret_manager_secret_iam_member" "titan_redis_auth" {
  secret_id = google_secret_manager_secret.redis_auth.secret_id
  project   = var.gcp_project
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.titan_aas.email}"
}

# ============================================
# Monitoring Access (for Prometheus)
# ============================================
resource "google_project_iam_member" "titan_monitoring_viewer" {
  project = var.gcp_project
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.titan_aas.email}"
}

resource "google_project_iam_member" "titan_monitoring_writer" {
  project = var.gcp_project
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.titan_aas.email}"
}

# ============================================
# Cloud Trace Access (for tracing)
# ============================================
resource "google_project_iam_member" "titan_trace_agent" {
  project = var.gcp_project
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.titan_aas.email}"
}
