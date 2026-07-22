variable "project_id" {
  type        = string
  description = "The GCP project ID"
}

variable "region" {
  type        = string
  description = "The GCP region"
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "The environment name"
  default     = "dev"
}

variable "db_password" {
  type        = string
  description = "Password for Cloud SQL PostgreSQL user"
  sensitive   = true
}
