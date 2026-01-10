# Titan-AAS GCP Cloud Storage

# ============================================
# Cloud Storage Bucket for Blobs
# ============================================
resource "google_storage_bucket" "blobs" {
  name     = "${var.project_name}-blobs-${var.gcp_project}"
  location = var.gcp_region
  project  = var.gcp_project

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 90
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  # CORS configuration for browser uploads
  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD", "PUT", "POST", "DELETE"]
    response_header = ["*"]
    max_age_seconds = 3600
  }

  labels = {
    project     = var.project_name
    environment = var.environment
  }
}

# ============================================
# Bucket IAM for Titan-AAS Service Account
# ============================================
resource "google_storage_bucket_iam_member" "titan_storage_admin" {
  bucket = google_storage_bucket.blobs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.titan_aas.email}"
}
