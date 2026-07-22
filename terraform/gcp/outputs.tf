output "vpc_name" {
  value = google_compute_network.vpc.name
}

output "gke_cluster_name" {
  value = google_container_cluster.primary.name
}

output "gke_cluster_endpoint" {
  value     = google_container_cluster.primary.endpoint
  sensitive = true
}

output "postgres_instance_name" {
  value = google_sql_database_instance.postgres.name
}

output "postgres_public_ip_address" {
  value = google_sql_database_instance.postgres.public_ip_address
}

output "storage_bucket_name" {
  value = google_storage_bucket.bucket.name
}
