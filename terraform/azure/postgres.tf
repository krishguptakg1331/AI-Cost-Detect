resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "${var.project_name}-${var.environment}-pg"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "14"
  delegated_subnet_id    = azurerm_subnet.postgres.id
  private_dns_zone_id    = azurerm_private_dns_zone.postgres.id
  administrator_login    = var.db_username
  administrator_password = var.db_password
  zone                   = "1"

  storage_mb   = 32768
  sku_name     = "B_Standard_B1ms"
  
  backup_retention_days = 7

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
  tags = var.tags
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "costdetective"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}
