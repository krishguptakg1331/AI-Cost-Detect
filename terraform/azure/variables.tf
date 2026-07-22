variable "project_name" {
  type        = string
  description = "The name of the project"
  default     = "cost-detective"
}

variable "environment" {
  type        = string
  description = "The environment name (e.g., dev, prod)"
  default     = "dev"
}

variable "location" {
  type        = string
  description = "The Azure region to deploy resources"
  default     = "East US"
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources"
  default = {
    Project     = "AI-Cloud-Cost-Detective"
    Environment = "dev"
    ManagedBy   = "Terraform"
  }
}

variable "db_username" {
  type        = string
  description = "The administrator login name for the PostgreSQL server"
  default     = "costdetective_admin"
}

variable "db_password" {
  type        = string
  description = "The administrator password for the PostgreSQL server"
  sensitive   = true
}

variable "aks_node_count" {
  type        = number
  description = "Number of nodes in the AKS default node pool"
  default     = 2
}

variable "aks_vm_size" {
  type        = string
  description = "The VM size for the AKS nodes"
  default     = "Standard_D2s_v3"
}
