resource "google_storage_bucket" "bucket" {
  name          = "costdetectivest-${var.project_id}-${var.environment}"
  location      = "US"
  force_destroy = true

  uniform_bucket_level_access = true
}
