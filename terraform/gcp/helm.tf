# Titan-AAS GCP Helm Release

# ============================================
# Kubernetes Namespace
# ============================================
resource "kubernetes_namespace" "titan" {
  metadata {
    name = "titan"

    labels = {
      name        = "titan"
      environment = var.environment
    }
  }

  depends_on = [google_container_node_pool.main]
}

# ============================================
# Kubernetes Secret for Database Credentials
# ============================================
resource "kubernetes_secret" "db_credentials" {
  metadata {
    name      = "titan-db-credentials"
    namespace = kubernetes_namespace.titan.metadata[0].name
  }

  data = {
    password = random_password.db_password.result
  }

  depends_on = [kubernetes_namespace.titan]
}

# ============================================
# Helm Release for Titan-AAS
# ============================================
resource "helm_release" "titan_aas" {
  name       = "titan"
  namespace  = kubernetes_namespace.titan.metadata[0].name
  chart      = "${path.module}/../../charts/titan-aas"
  timeout    = 600
  wait       = true

  values = [
    yamlencode({
      replicaCount = var.environment == "production" ? 3 : 2

      image = {
        repository = var.titan_image_repository
        tag        = var.titan_image_tag
      }

      serviceAccount = {
        create = true
        annotations = {
          "iam.gke.io/gcp-service-account" = google_service_account.titan_aas.email
        }
      }

      ingress = {
        enabled   = true
        className = "gce"
        annotations = {
          "kubernetes.io/ingress.global-static-ip-name" = google_compute_global_address.ingress.name
          "kubernetes.io/ingress.class"                 = "gce"
        }
        hosts = var.domain_name != "" ? [
          {
            host = var.domain_name
            paths = [
              {
                path     = "/"
                pathType = "Prefix"
              }
            ]
          }
        ] : []
        tls = var.domain_name != "" ? [
          {
            secretName = "titan-tls"
            hosts      = [var.domain_name]
          }
        ] : []
      }

      autoscaling = {
        enabled                        = true
        minReplicas                    = var.environment == "production" ? 3 : 2
        maxReplicas                    = var.environment == "production" ? 20 : 5
        targetCPUUtilizationPercentage = 70
      }

      resources = {
        requests = {
          cpu    = "500m"
          memory = "512Mi"
        }
        limits = {
          cpu    = "2000m"
          memory = "2Gi"
        }
      }

      # Disable embedded PostgreSQL - use Cloud SQL
      postgresql = {
        enabled = false
      }

      externalDatabase = {
        host           = google_sql_database_instance.main.private_ip_address
        port           = 5432
        database       = "titan"
        username       = "titan"
        existingSecret = kubernetes_secret.db_credentials.metadata[0].name
      }

      # Disable embedded Redis - use Memorystore
      redis = {
        enabled = false
      }

      externalRedis = {
        host = google_redis_instance.main.host
        port = google_redis_instance.main.port
        # Auth handled via Workload Identity accessing Secret Manager
      }

      blobStorage = {
        type = "gcs"
        gcs = {
          bucket = google_storage_bucket.blobs.name
        }
      }

      env = {
        TITAN_ENV        = var.environment
        GCP_PROJECT      = var.gcp_project
        ENABLE_TRACING   = "true"
        ENABLE_METRICS   = "true"
      }

      observability = {
        tracing = {
          enabled = true
        }
        metrics = {
          enabled = true
          serviceMonitor = {
            enabled = true
          }
        }
      }

      networkPolicy = {
        enabled = true
      }
    })
  ]

  depends_on = [
    google_container_node_pool.main,
    google_sql_database_instance.main,
    google_redis_instance.main,
    google_storage_bucket.blobs,
    google_service_account_iam_member.titan_workload_identity,
    kubernetes_secret.db_credentials,
  ]
}
