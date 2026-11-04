output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "storage_account" {
  value = azurerm_storage_account.lake.name
}

output "key_vault" {
  value = azurerm_key_vault.main.name
}

output "jobs_identity_client_id" {
  value = azurerm_user_assigned_identity.jobs.client_id
}

output "environment" {
  value = azurerm_container_app_environment.main.name
}
