###############################################################################
# AI Cloud Cost Detective — AWS Infrastructure
# 
# This Terraform configuration provisions all AWS resources needed for the
# AI Cloud Cost Detective application (adapted from Azure to AWS).
#
# Resources provisioned:
#   - VPC with public/private subnets
#   - EKS Cluster (Kubernetes)
#   - RDS PostgreSQL (Managed Database)
#   - S3 Bucket (Storage)
#   - Secrets Manager (API Keys & Credentials)
#   - IAM Roles & Policies
#   - Security Groups
#   - NAT Gateway & Internet Gateway
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Uncomment and configure for remote state storage
  # backend "s3" {
  #   bucket         = "cost-detective-tfstate"
  #   key            = "terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "cost-detective-tfstate-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Application = "ai-cost-detective"
    }
  }
}

###############################################################################
# Data Sources
###############################################################################

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
