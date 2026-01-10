# Titan-AAS Azure Helm Release

# ============================================
# Kubernetes Namespace
# ============================================
resource "kubernetes_namespace" "titan" {
  metadata {
    name = var.kubernetes_namespace

    labels = {
      name        = var.kubernetes_namespace
      environment = var.environment
    }
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}

# ============================================
# Kubernetes Secrets for Database
# ============================================
resource "kubernetes_secret" "db_credentials" {
  metadata {
    name      = "${var.project_name}-db-credentials"
    namespace = kubernetes_namespace.titan.metadata[0].name
  }

  data = {
    host     = azurerm_postgresql_flexible_server.main.fqdn
    port     = "5432"
    database = azurerm_postgresql_flexible_server_database.titan.name
    username = azurerm_postgresql_flexible_server.main.administrator_login
    password = random_password.db_password.result
    url      = "postgresql://${azurerm_postgresql_flexible_server.main.administrator_login}:${random_password.db_password.result}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.titan.name}?sslmode=require"
  }

  type = "Opaque"
}

# ============================================
# Kubernetes Secrets for Redis
# ============================================
resource "kubernetes_secret" "redis_credentials" {
  metadata {
    name      = "${var.project_name}-redis-credentials"
    namespace = kubernetes_namespace.titan.metadata[0].name
  }

  data = {
    host     = azurerm_redis_cache.main.hostname
    port     = tostring(azurerm_redis_cache.main.ssl_port)
    password = azurerm_redis_cache.main.primary_access_key
    url      = "rediss://:${azurerm_redis_cache.main.primary_access_key}@${azurerm_redis_cache.main.hostname}:${azurerm_redis_cache.main.ssl_port}"
  }

  type = "Opaque"
}

# ============================================
# Kubernetes Secrets for Storage
# ============================================
resource "kubernetes_secret" "storage_credentials" {
  metadata {
    name      = "${var.project_name}-storage-credentials"
    namespace = kubernetes_namespace.titan.metadata[0].name
  }

  data = {
    account_name   = azurerm_storage_account.main.name
    account_key    = azurerm_storage_account.main.primary_access_key
    container_name = azurerm_storage_container.aasx.name
  }

  type = "Opaque"
}

# ============================================
# Helm Release
# ============================================
resource "helm_release" "titan" {
  name       = var.project_name
  namespace  = kubernetes_namespace.titan.metadata[0].name
  chart      = var.helm_chart_path
  version    = var.helm_chart_version
  wait       = true
  timeout    = 600

  # Application settings
  set {
    name  = "image.repository"
    value = var.titan_image_repository
  }

  set {
    name  = "image.tag"
    value = var.titan_image_tag
  }

  set {
    name  = "replicaCount"
    value = var.environment == "production" ? "3" : "2"
  }

  # Workload Identity
  set {
    name  = "serviceAccount.annotations.azure\\.workload\\.identity/client-id"
    value = azurerm_user_assigned_identity.titan.client_id
  }

  set {
    name  = "podLabels.azure\\.workload\\.identity/use"
    value = "true"
  }

  # External Database (PostgreSQL)
  set {
    name  = "postgresql.enabled"
    value = "false"
  }

  set {
    name  = "externalDatabase.enabled"
    value = "true"
  }

  set {
    name  = "externalDatabase.existingSecret"
    value = kubernetes_secret.db_credentials.metadata[0].name
  }

  set {
    name  = "externalDatabase.existingSecretHostKey"
    value = "host"
  }

  set {
    name  = "externalDatabase.existingSecretPortKey"
    value = "port"
  }

  set {
    name  = "externalDatabase.existingSecretDatabaseKey"
    value = "database"
  }

  set {
    name  = "externalDatabase.existingSecretUserKey"
    value = "username"
  }

  set {
    name  = "externalDatabase.existingSecretPasswordKey"
    value = "password"
  }

  # External Redis
  set {
    name  = "redis.enabled"
    value = "false"
  }

  set {
    name  = "externalRedis.enabled"
    value = "true"
  }

  set {
    name  = "externalRedis.existingSecret"
    value = kubernetes_secret.redis_credentials.metadata[0].name
  }

  set {
    name  = "externalRedis.existingSecretHostKey"
    value = "host"
  }

  set {
    name  = "externalRedis.existingSecretPortKey"
    value = "port"
  }

  set {
    name  = "externalRedis.existingSecretPasswordKey"
    value = "password"
  }

  set {
    name  = "externalRedis.tls"
    value = "true"
  }

  # Azure Blob Storage
  set {
    name  = "blobStorage.type"
    value = "azure"
  }

  set {
    name  = "blobStorage.azure.existingSecret"
    value = kubernetes_secret.storage_credentials.metadata[0].name
  }

  set {
    name  = "blobStorage.azure.existingSecretAccountNameKey"
    value = "account_name"
  }

  set {
    name  = "blobStorage.azure.existingSecretAccountKeyKey"
    value = "account_key"
  }

  set {
    name  = "blobStorage.azure.existingSecretContainerKey"
    value = "container_name"
  }

  # Ingress
  set {
    name  = "ingress.enabled"
    value = "true"
  }

  set {
    name  = "ingress.className"
    value = "nginx"
  }

  set {
    name  = "ingress.hosts[0].host"
    value = var.domain_name
  }

  set {
    name  = "ingress.hosts[0].paths[0].path"
    value = "/"
  }

  set {
    name  = "ingress.hosts[0].paths[0].pathType"
    value = "Prefix"
  }

  set {
    name  = "ingress.tls[0].secretName"
    value = "${var.project_name}-tls"
  }

  set {
    name  = "ingress.tls[0].hosts[0]"
    value = var.domain_name
  }

  # Resource requests/limits
  set {
    name  = "resources.requests.cpu"
    value = "250m"
  }

  set {
    name  = "resources.requests.memory"
    value = "512Mi"
  }

  set {
    name  = "resources.limits.cpu"
    value = "1000m"
  }

  set {
    name  = "resources.limits.memory"
    value = "1Gi"
  }

  # Health checks
  set {
    name  = "livenessProbe.enabled"
    value = "true"
  }

  set {
    name  = "readinessProbe.enabled"
    value = "true"
  }

  # Observability
  set {
    name  = "metrics.enabled"
    value = "true"
  }

  set {
    name  = "tracing.enabled"
    value = "true"
  }

  depends_on = [
    azurerm_kubernetes_cluster.main,
    azurerm_kubernetes_cluster_node_pool.main,
    azurerm_postgresql_flexible_server.main,
    azurerm_redis_cache.main,
    azurerm_storage_account.main,
    azurerm_federated_identity_credential.titan,
    kubernetes_secret.db_credentials,
    kubernetes_secret.redis_credentials,
    kubernetes_secret.storage_credentials
  ]
}

# ============================================
# NGINX Ingress Controller (optional)
# ============================================
resource "helm_release" "nginx_ingress" {
  count = var.install_nginx_ingress ? 1 : 0

  name             = "ingress-nginx"
  namespace        = "ingress-nginx"
  create_namespace = true
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = "4.9.0"
  wait             = true
  timeout          = 300

  set {
    name  = "controller.service.annotations.service\\.beta\\.kubernetes\\.io/azure-load-balancer-health-probe-request-path"
    value = "/healthz"
  }

  set {
    name  = "controller.replicaCount"
    value = var.environment == "production" ? "3" : "2"
  }

  set {
    name  = "controller.resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "controller.resources.requests.memory"
    value = "128Mi"
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}

# ============================================
# cert-manager for TLS certificates (optional)
# ============================================
resource "helm_release" "cert_manager" {
  count = var.install_cert_manager ? 1 : 0

  name             = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = true
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  version          = "v1.14.0"
  wait             = true
  timeout          = 300

  set {
    name  = "installCRDs"
    value = "true"
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}
