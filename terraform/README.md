# Titan-AAS Terraform Deployments

This directory contains Terraform configurations for deploying Titan-AAS to cloud providers.

## Available Providers

| Provider | Directory | Status |
|----------|-----------|--------|
| AWS | `aws/` | Complete |
| GCP | `gcp/` | Complete |
| Azure | `azure/` | Complete |

## Quick Start

Choose your cloud provider and follow the deployment instructions below.

---

## AWS Deployment

### Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.5.0
3. **kubectl** for Kubernetes access
4. **Helm** >= 3.12

### Quick Start

```bash
cd aws

# Initialize Terraform
terraform init

# Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Preview changes
terraform plan

# Apply changes
terraform apply
```

### What Gets Created

- **VPC** with public and private subnets across 3 AZs
- **EKS Cluster** with managed node groups
- **RDS PostgreSQL** with automated backups and encryption
- **ElastiCache Redis** with encryption in transit/at rest
- **S3 Bucket** for blob storage with versioning
- **IAM Roles** for IRSA (pod-level IAM)
- **AWS Load Balancer Controller** for ingress
- **Titan-AAS Helm Release** with all configurations

### Architecture

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                         AWS Region                          │
                          │                                                             │
    ┌─────────┐           │  ┌──────────────────────────────────────────────────────┐  │
    │  Users  │───────────┼──│                    ALB (Ingress)                     │  │
    └─────────┘           │  └───────────────────────────┬──────────────────────────┘  │
                          │                              │                              │
                          │  ┌───────────────────────────┴──────────────────────────┐  │
                          │  │                     EKS Cluster                       │  │
                          │  │                                                       │  │
                          │  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
                          │  │   │ Titan Pod 1 │  │ Titan Pod 2 │  │ Titan Pod 3 │  │  │
                          │  │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │  │
                          │  │          │                │                │          │  │
                          │  └──────────┼────────────────┼────────────────┼──────────┘  │
                          │             │                │                │              │
                          │  ┌──────────┴────────────────┴────────────────┴──────────┐  │
                          │  │                    Private Subnets                     │  │
                          │  │                                                        │  │
                          │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
                          │  │  │     RDS      │  │  ElastiCache │  │      S3      │ │  │
                          │  │  │  PostgreSQL  │  │    Redis     │  │    Blobs     │ │  │
                          │  │  └──────────────┘  └──────────────┘  └──────────────┘ │  │
                          │  └────────────────────────────────────────────────────────┘  │
                          └─────────────────────────────────────────────────────────────┘
```

### Configuration

#### Required Variables

| Variable | Description |
|----------|-------------|
| `domain_name` | Domain for the application (e.g., `aas.example.com`) |
| `acm_certificate_arn` | ACM certificate ARN for HTTPS |
| `titan_image_repository` | Docker image repository |
| `titan_image_tag` | Docker image tag to deploy |

#### Environment-Specific Settings

**Development:**
```hcl
environment         = "development"
node_instance_types = ["t3.medium"]
node_min_size       = 2
node_max_size       = 5
db_instance_class   = "db.t3.medium"
redis_node_type     = "cache.t3.micro"
```

**Production:**
```hcl
environment         = "production"
node_instance_types = ["t3.large", "t3.xlarge"]
node_min_size       = 3
node_max_size       = 20
db_instance_class   = "db.r6g.large"
redis_node_type     = "cache.r6g.large"
```

### Post-Deployment

1. **Configure kubectl:**
   ```bash
   aws eks update-kubeconfig --region us-east-1 --name titan-aas-cluster
   ```

2. **Verify deployment:**
   ```bash
   kubectl get pods -n titan
   kubectl get svc -n titan
   ```

3. **Configure DNS:**
   - Get the ALB DNS name from the ingress
   - Create a CNAME record pointing your domain to the ALB

4. **Access the application:**
   ```bash
   curl https://aas.yourdomain.com/health
   ```

### Costs (Estimated)

| Component | Development | Production |
|-----------|-------------|------------|
| EKS Control Plane | $73/month | $73/month |
| EC2 Nodes (t3.medium x 3) | ~$90/month | - |
| EC2 Nodes (t3.large x 5) | - | ~$300/month |
| RDS (db.t3.medium) | ~$50/month | - |
| RDS (db.r6g.large, Multi-AZ) | - | ~$400/month |
| ElastiCache | ~$15/month | ~$200/month |
| NAT Gateway | ~$45/month | ~$135/month |
| **Total** | ~$275/month | ~$1,100/month |

### Remote State (AWS)

For team collaboration, configure S3 backend:

```hcl
terraform {
  backend "s3" {
    bucket         = "titan-aas-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "titan-aas-terraform-locks"
    encrypt        = true
  }
}
```

---

## GCP Deployment

### Prerequisites

1. **Google Cloud SDK** (`gcloud`) configured with appropriate credentials
2. **Terraform** >= 1.5.0
3. **kubectl** for Kubernetes access
4. **Helm** >= 3.12
5. **Enabled APIs:** Compute Engine, GKE, Cloud SQL, Memorystore, Secret Manager

### Quick Start

```bash
cd gcp

# Authenticate with GCP
gcloud auth application-default login

# Initialize Terraform
terraform init

# Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Preview changes
terraform plan

# Apply changes
terraform apply
```

### What Gets Created

- **VPC** with private subnet and secondary ranges for pods/services
- **Cloud Router + Cloud NAT** for outbound connectivity
- **GKE Cluster** with Workload Identity and private nodes
- **Cloud SQL PostgreSQL 16** with private IP and automated backups
- **Memorystore Redis 7.0** with TLS and HA
- **Cloud Storage** bucket for AASX files
- **Service Account** with Workload Identity binding
- **Managed SSL Certificate** for ingress
- **Titan-AAS Helm Release** with all configurations

### Architecture

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                       GCP Project                           │
                          │                                                             │
    ┌─────────┐           │  ┌──────────────────────────────────────────────────────┐  │
    │  Users  │───────────┼──│               GKE Ingress + Managed SSL              │  │
    └─────────┘           │  └───────────────────────────┬──────────────────────────┘  │
                          │                              │                              │
                          │  ┌───────────────────────────┴──────────────────────────┐  │
                          │  │              GKE Cluster (Private Nodes)              │  │
                          │  │                                                       │  │
                          │  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
                          │  │   │ Titan Pod 1 │  │ Titan Pod 2 │  │ Titan Pod 3 │  │  │
                          │  │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │  │
                          │  │          │     Workload Identity     │               │  │
                          │  └──────────┼────────────────┼────────────────┼──────────┘  │
                          │             │                │                │              │
                          │  ┌──────────┴────────────────┴────────────────┴──────────┐  │
                          │  │                VPC with Private Services Access        │  │
                          │  │                                                        │  │
                          │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
                          │  │  │   Cloud SQL  │  │  Memorystore │  │ Cloud Storage│ │  │
                          │  │  │  PostgreSQL  │  │    Redis     │  │    Blobs     │ │  │
                          │  │  └──────────────┘  └──────────────┘  └──────────────┘ │  │
                          │  └────────────────────────────────────────────────────────┘  │
                          └─────────────────────────────────────────────────────────────┘
```

### Configuration

#### Required Variables

| Variable | Description |
|----------|-------------|
| `gcp_project` | GCP project ID |
| `gcp_region` | GCP region (e.g., `us-central1`) |
| `domain_name` | Domain for the application |
| `titan_image_repository` | Docker image repository |
| `titan_image_tag` | Docker image tag to deploy |

#### Environment-Specific Settings

**Development:**
```hcl
environment       = "development"
node_machine_type = "e2-standard-2"
node_min_size     = 2
node_max_size     = 5
db_tier           = "db-custom-2-8192"
redis_memory_size_gb = 1
```

**Production:**
```hcl
environment       = "production"
node_machine_type = "e2-standard-4"
node_min_size     = 3
node_max_size     = 20
db_tier           = "db-custom-4-16384"
redis_memory_size_gb = 4
```

### Post-Deployment

1. **Configure kubectl:**
   ```bash
   gcloud container clusters get-credentials titan-aas-prod --region us-central1
   ```

2. **Verify deployment:**
   ```bash
   kubectl get pods -n titan
   kubectl get svc -n titan
   ```

3. **Configure DNS:**
   - Get the static IP from Terraform outputs
   - Create an A record pointing your domain to the IP

4. **Access the application:**
   ```bash
   curl https://aas.yourdomain.com/health
   ```

### Costs (Estimated)

| Component | Development | Production |
|-----------|-------------|------------|
| GKE Control Plane | Free* | Free* |
| Compute (e2-standard-2 x 3) | ~$75/month | - |
| Compute (e2-standard-4 x 5) | - | ~$250/month |
| Cloud SQL | ~$40/month | ~$300/month |
| Memorystore Redis | ~$30/month | ~$150/month |
| Cloud NAT | ~$30/month | ~$90/month |
| Cloud Storage | ~$5/month | ~$20/month |
| **Total** | ~$180/month | ~$810/month |

*GKE Autopilot or first zonal cluster has free control plane

### Remote State (GCP)

Configure GCS backend:

```hcl
terraform {
  backend "gcs" {
    bucket = "titan-aas-terraform-state"
    prefix = "production"
  }
}
```

Create the backend bucket:

```bash
gsutil mb -l us-central1 gs://titan-aas-terraform-state
gsutil versioning set on gs://titan-aas-terraform-state
```

---

## Azure Deployment

### Prerequisites

1. **Azure CLI** (`az`) configured with appropriate credentials
2. **Terraform** >= 1.5.0
3. **kubectl** for Kubernetes access
4. **Helm** >= 3.12

### Quick Start

```bash
cd azure

# Authenticate with Azure
az login

# Initialize Terraform
terraform init

# Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Preview changes
terraform plan

# Apply changes
terraform apply
```

### What Gets Created

- **Resource Group** for all resources
- **VNet** with subnets for AKS, PostgreSQL, and Private Endpoints
- **NAT Gateway** with static public IP
- **AKS Cluster** with Workload Identity and Azure CNI
- **PostgreSQL Flexible Server** with private access and zone redundancy
- **Azure Cache for Redis Premium** with Private Endpoint
- **Storage Account** with Private Endpoint for blob storage
- **Key Vault** for secrets management
- **User-Assigned Managed Identity** with Workload Identity binding
- **NGINX Ingress Controller** and **cert-manager** (optional)
- **Titan-AAS Helm Release** with all configurations

### Architecture

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                     Azure Resource Group                    │
                          │                                                             │
    ┌─────────┐           │  ┌──────────────────────────────────────────────────────┐  │
    │  Users  │───────────┼──│              NGINX Ingress + cert-manager            │  │
    └─────────┘           │  └───────────────────────────┬──────────────────────────┘  │
                          │                              │                              │
                          │  ┌───────────────────────────┴──────────────────────────┐  │
                          │  │              AKS Cluster (Azure CNI)                  │  │
                          │  │                                                       │  │
                          │  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
                          │  │   │ Titan Pod 1 │  │ Titan Pod 2 │  │ Titan Pod 3 │  │  │
                          │  │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │  │
                          │  │          │     Workload Identity     │               │  │
                          │  └──────────┼────────────────┼────────────────┼──────────┘  │
                          │             │                │                │              │
                          │  ┌──────────┴────────────────┴────────────────┴──────────┐  │
                          │  │           VNet with Private Endpoints                  │  │
                          │  │                                                        │  │
                          │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
                          │  │  │  PostgreSQL  │  │ Azure Cache  │  │   Storage    │ │  │
                          │  │  │   Flexible   │  │  for Redis   │  │   Account    │ │  │
                          │  │  └──────────────┘  └──────────────┘  └──────────────┘ │  │
                          │  │                                                        │  │
                          │  │  ┌────────────────────────────────────────────────────┐│  │
                          │  │  │                    Key Vault                       ││  │
                          │  │  └────────────────────────────────────────────────────┘│  │
                          │  └────────────────────────────────────────────────────────┘  │
                          └─────────────────────────────────────────────────────────────┘
```

### Configuration

#### Required Variables

| Variable | Description |
|----------|-------------|
| `azure_region` | Azure region (e.g., `eastus`) |
| `project_name` | Project name for resource naming |
| `domain_name` | Domain for the application |
| `titan_image_repository` | Docker image repository |
| `titan_image_tag` | Docker image tag to deploy |

#### Environment-Specific Settings

**Development:**
```hcl
environment       = "development"
node_vm_size      = "Standard_D2s_v3"
node_min_size     = 2
node_max_size     = 5
db_sku_name       = "GP_Standard_D2s_v3"
db_storage_mb     = 32768
redis_capacity    = 1
```

**Production:**
```hcl
environment       = "production"
node_vm_size      = "Standard_D4s_v3"
node_min_size     = 3
node_max_size     = 20
db_sku_name       = "GP_Standard_D4s_v3"
db_storage_mb     = 65536
redis_capacity    = 2
```

### Post-Deployment

1. **Configure kubectl:**
   ```bash
   az aks get-credentials --resource-group titan-aas-production-rg --name titan-aas-cluster
   ```

2. **Verify deployment:**
   ```bash
   kubectl get pods -n titan
   kubectl get svc -n titan
   ```

3. **Configure DNS:**
   - Get the ingress external IP
   - Create an A record pointing your domain to the IP

4. **Access the application:**
   ```bash
   curl https://aas.yourdomain.com/health
   ```

### Costs (Estimated)

| Component | Development | Production |
|-----------|-------------|------------|
| AKS Control Plane | Free | Free |
| VMs (D2s_v3 x 3) | ~$100/month | - |
| VMs (D4s_v3 x 5) | - | ~$350/month |
| PostgreSQL Flexible | ~$60/month | ~$300/month |
| Azure Cache for Redis | ~$80/month | ~$160/month |
| NAT Gateway | ~$35/month | ~$35/month |
| Storage Account | ~$5/month | ~$20/month |
| **Total** | ~$280/month | ~$865/month |

### Remote State (Azure)

Configure Azure Storage backend:

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "titan-aas-tfstate-rg"
    storage_account_name = "titanaastfstate"
    container_name       = "tfstate"
    key                  = "production.tfstate"
  }
}
```

Create the backend resources:

```bash
# Create resource group
az group create --name titan-aas-tfstate-rg --location eastus

# Create storage account
az storage account create \
  --name titanaastfstate \
  --resource-group titan-aas-tfstate-rg \
  --sku Standard_LRS \
  --encryption-services blob

# Create container
az storage container create \
  --name tfstate \
  --account-name titanaastfstate
```

---

## Cross-Cloud Comparison

| Feature | AWS | GCP | Azure |
|---------|-----|-----|-------|
| Kubernetes | EKS | GKE | AKS |
| Database | RDS PostgreSQL | Cloud SQL | PostgreSQL Flexible Server |
| Cache | ElastiCache Redis | Memorystore | Azure Cache for Redis |
| Blob Storage | S3 | Cloud Storage | Blob Storage |
| Pod Identity | IRSA | Workload Identity | Workload Identity |
| Private Access | VPC Endpoints | Private Services Access | Private Endpoints |
| Secrets | Secrets Manager | Secret Manager | Key Vault |
| Ingress | AWS LB Controller | GKE Ingress | NGINX Ingress |

---

## Security Considerations

All cloud deployments include:

- **Encryption at Rest:** Databases, caches, and storage are encrypted
- **Encryption in Transit:** TLS 1.2+ for all connections
- **Pod Identity:** No static credentials in pods (IRSA/Workload Identity)
- **Private Networking:** Databases and caches use private endpoints
- **Network Policies:** Restrict pod-to-pod communication
- **Key Management:** Secrets stored in cloud-native vaults

---

## Cleanup

### AWS
```bash
cd aws
terraform destroy
```

### GCP
```bash
cd gcp
terraform destroy
```

### Azure
```bash
cd azure
terraform destroy
```

**Note:** Production environments have deletion protection enabled for databases and storage. You may need to disable protection before destruction.

---

## Troubleshooting

### Common Issues

#### Pods Not Starting

Check pod events:
```bash
kubectl describe pod <pod-name> -n titan
kubectl logs <pod-name> -n titan
```

#### Database Connection Failed

Verify network connectivity:
```bash
# Check if pod can reach database
kubectl exec -it <pod-name> -n titan -- nc -zv <db-host> 5432
```

#### Redis Connection Failed

Check Redis endpoint:
```bash
kubectl exec -it <pod-name> -n titan -- redis-cli -h <redis-host> -p 6379 --tls ping
```

#### Ingress Not Working

Check ingress controller logs:
```bash
# AWS
kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# GCP
kubectl logs -n kube-system -l k8s-app=glbc

# Azure
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx
```

### Getting Help

- Check the [deployment runbook](../docs/deployment-runbook.md)
- Review [API documentation](../docs/api-guide.md)
- File an issue at https://github.com/your-org/titan-aas/issues
