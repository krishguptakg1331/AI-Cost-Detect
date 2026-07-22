resource "google_sql_database_instance" "postgres" {
  name             = "cost-detective-${var.environment}-pg"
  database_version = "POSTGRES_14"
  region           = var.region

  settings {
    tier = "db-f1-micro"
    
    ip_configuration {
      ipv4_enabled    = true
    }
  }
  
  deletion_protection = false
}

resource "google_sql_database" "database" {
  name     = "costdetective"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "users" {
  name     = "costdetective_admin"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}
