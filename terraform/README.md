# AI Cloud Cost Detective — AWS Terraform Infrastructure

## Architecture Overview

This Terraform configuration provisions the complete AWS infrastructure for the AI Cloud Cost Detective application.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          AWS Account                                │
│                                                                     │
│  ┌───────────────────── VPC (10.0.0.0/16) ───────────────────────┐ │
│  │                                                                │ │
│  │  ┌─────────── Public Subnets ───────────┐                     │ │
│  │  │  AZ-a: 10.0.1.0/24                   │  ← ALB, NAT GW     │ │
│  │  │  AZ-b: 10.0.2.0/24                   │                     │ │
│  │  │  AZ-c: 10.0.3.0/24                   │                     │ │
│  │  └───────────────────────────────────────┘                     │ │
│  │                                                                │ │
│  │  ┌─────────── Private Subnets ──────────┐                     │ │
│  │  │  AZ-a: 10.0.11.0/24                  │  ← EKS Nodes       │ │
│  │  │  AZ-b: 10.0.12.0/24                  │                     │ │
│  │  │  AZ-c: 10.0.13.0/24                  │                     │ │
│  │  └───────────────────────────────────────┘                     │ │
│  │                                                                │ │
│  │  ┌─────────── Database Subnets ─────────┐                     │ │
│  │  │  AZ-a: 10.0.21.0/24                  │  ← RDS PostgreSQL  │ │
│  │  │  AZ-b: 10.0.22.0/24                  │                     │ │
│  │  │  AZ-c: 10.0.23.0/24                  │                     │ │
│  │  └───────────────────────────────────────┘                     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──── EKS ────┐  ┌─── RDS ────┐  ┌── S3 ──┐  ┌── Secrets ──┐    │
│  │ K8s 1.30    │  │ PG 16.3    │  │ Storage │  │ OpenAI Key  │    │
│  │ 2x t3.med  │  │ t3.micro   │  │ Reports │  │ JWT Secret  │    │
│  │ Auto 1-4   │  │ Encrypted  │  │ Logs    │  │ DB Creds    │    │
│  └─────────────┘  └────────────┘  └─────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

## Resources Created

| Resource | AWS Service | Purpose |
|----------|-------------|---------|
| VPC | Amazon VPC | Isolated network with 3-tier subnets |
| EKS Cluster | Amazon EKS | Kubernetes for running backend & frontend |
| Node Group | EC2 (Managed) | Worker nodes for EKS (t3.medium, 1-4 nodes) |
| RDS Instance | Amazon RDS | PostgreSQL 16.3 for users & analyses |
| S3 Bucket | Amazon S3 | Storage for reports & VPC flow logs |
| Secrets | Secrets Manager | OpenAI key, JWT secret, DB credentials |
| IAM Roles | AWS IAM | EKS cluster, nodes, and app roles (IRSA) |
| Security Groups | VPC SGs | Network access control for all resources |
| NAT Gateway | VPC NAT | Outbound internet for private subnets |
| CloudWatch | CloudWatch Logs | EKS cluster logging |
| OIDC Provider | IAM OIDC | IAM Roles for Service Accounts |

## Prerequisites

- **AWS CLI** installed and configured (`aws configure`)
- **Terraform** >= 1.5.0
- **AWS Account** with sufficient permissions
- An **OpenAI API key**

## Quick Start

```bash
# 1. Clone and navigate to terraform directory
cd terraform

# 2. Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# 3. Initialize Terraform
terraform init

# 4. Review the plan
terraform plan

# 5. Apply (pass sensitive vars via CLI)
terraform apply \
  -var="openai_api_key=sk-your-key-here"

# 6. Configure kubectl
aws eks update-kubeconfig \
  --name cost-detective-dev-eks \
  --region us-east-1
```

## File Structure

```
terraform/
├── main.tf                  # Provider config, versions, data sources
├── variables.tf             # All input variables
├── outputs.tf               # All outputs
├── vpc.tf                   # VPC, subnets, NAT, IGW, route tables
├── security_groups.tf       # Security groups for EKS, RDS, ALB
├── iam.tf                   # IAM roles & policies (EKS, IRSA, app)
├── eks.tf                   # EKS cluster, node group, add-ons, OIDC
├── rds.tf                   # RDS PostgreSQL instance
├── s3.tf                    # S3 bucket with lifecycle policies
├── secrets.tf               # Secrets Manager (OpenAI, JWT, DB creds)
├── terraform.tfvars         # Your environment values (gitignored)
├── terraform.tfvars.example # Example values (safe to commit)
├── .gitignore               # Ignores state, .terraform, secrets
└── README.md                # This file
```

## Key Design Decisions

1. **3-Tier Subnet Architecture** — Public (ALB), Private (EKS), Database (RDS) for defense-in-depth
2. **IRSA** — IAM Roles for Service Accounts so pods get least-privilege AWS access without embedding credentials
3. **AWS Cost Explorer Access** — The app IAM role has read-only access to Cost Explorer & resource discovery APIs (AWS equivalent of `az resource list`)
4. **Auto-generated Secrets** — DB password and JWT secret are auto-generated and stored in Secrets Manager
5. **Single NAT Gateway** — Cost-optimized for dev; for prod, deploy one per AZ
6. **S3 Lifecycle Policies** — Auto-tier reports to IA→Glacier→Delete for cost savings

## Sensitive Values

Never commit secrets to version control. Use one of these methods:

```bash
# Option 1: CLI flags
terraform apply -var="openai_api_key=sk-..."

# Option 2: Environment variables
export TF_VAR_openai_api_key="sk-..."
export TF_VAR_jwt_secret_key="your-secret"
terraform apply

# Option 3: Separate tfvars file (gitignored)
terraform apply -var-file="secrets.tfvars"
```

## Outputs

After `terraform apply`, you'll get:

| Output | Description |
|--------|-------------|
| `eks_cluster_name` | EKS cluster name |
| `eks_cluster_endpoint` | K8s API server endpoint |
| `eks_kubeconfig_command` | Command to configure kubectl |
| `rds_endpoint` | PostgreSQL connection endpoint |
| `s3_bucket_name` | S3 bucket for storage |
| `secrets_*_arn` | ARNs for all secrets |
| `app_role_arn` | IAM role ARN for K8s service account |

## Cleanup

```bash
# Destroy all resources
terraform destroy

# If deletion protection is enabled on RDS (prod):
terraform destroy -target=aws_db_instance.main -var="db_deletion_protection=false"
terraform destroy
```
