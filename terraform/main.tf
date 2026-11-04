data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

locals {
  suffix = random_string.suffix.result
  tags = {
    project = "sydney-transit-intelligence-platform"
    managed = "terraform"
  }
  kv_uri = azurerm_key_vault.main.vault_uri
}

resource "azurerm_resource_group" "main" {
  name     = "${var.name_prefix}-rg"
  location = var.location
  tags     = local.tags
}

# ---------------------------------------------------------------- storage (raw archive + extracts)
resource "azurerm_storage_account" "lake" {
  name                            = "${var.name_prefix}lake${local.suffix}"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true # ADLS Gen2
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "raw" {
  name                  = "raw"
  storage_account_id    = azurerm_storage_account.lake.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "extracts" {
  name                  = "extracts"
  storage_account_id    = azurerm_storage_account.lake.id
  container_access_type = "private"
}

# ---------------------------------------------------------------- logs
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.name_prefix}-logs"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5 # hard cap so a log storm cannot run up a bill
  tags                = local.tags
}

# ---------------------------------------------------------------- identity and secrets
resource "azurerm_user_assigned_identity" "jobs" {
  name                = "${var.name_prefix}-jobs-identity"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

resource "azurerm_key_vault" "main" {
  name                       = "${var.name_prefix}-kv-${local.suffix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false # keeps teardown simple for a short-lived deployment
  tags                       = local.tags
}

# The identity the jobs run as: read secrets, write blobs, nothing else.
resource "azurerm_role_assignment" "jobs_read_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.jobs.principal_id
}

resource "azurerm_role_assignment" "jobs_write_blobs" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.jobs.principal_id
}

# Whoever runs the first apply can load the secrets (az keyvault secret set).
resource "azurerm_role_assignment" "deployer_manage_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ---------------------------------------------------------------- jobs
resource "azurerm_container_app_environment" "main" {
  name                       = "${var.name_prefix}-env"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

resource "azurerm_container_app_job" "ingest" {
  count                        = var.deploy_jobs ? 1 : 0
  name                         = "${var.name_prefix}-ingest"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  container_app_environment_id = azurerm_container_app_environment.main.id
  replica_timeout_in_seconds   = 300
  replica_retry_limit          = 0
  tags                         = local.tags

  schedule_trigger_config {
    cron_expression          = var.ingest_cron
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.jobs.id]
  }

  secret {
    name                = "tfnsw-api-key"
    identity            = azurerm_user_assigned_identity.jobs.id
    key_vault_secret_id = "${local.kv_uri}secrets/tfnsw-api-key"
  }

  template {
    container {
      name   = "ingest"
      image  = var.image
      args   = ["ingest"]
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "AZURE_STORAGE_ACCOUNT"
        value = azurerm_storage_account.lake.name
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.jobs.client_id
      }
      env {
        name        = "TFNSW_API_KEY"
        secret_name = "tfnsw-api-key"
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.jobs_read_secrets,
    azurerm_role_assignment.jobs_write_blobs,
    azurerm_storage_container.raw,
  ]
}

resource "azurerm_container_app_job" "transform" {
  count                        = var.deploy_jobs ? 1 : 0
  name                         = "${var.name_prefix}-transform"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  container_app_environment_id = azurerm_container_app_environment.main.id
  replica_timeout_in_seconds   = 1500
  replica_retry_limit          = 0
  tags                         = local.tags

  schedule_trigger_config {
    cron_expression          = var.transform_cron
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.jobs.id]
  }

  dynamic "secret" {
    for_each = toset(["tfnsw-api-key", "databricks-host", "databricks-http-path", "databricks-token"])
    content {
      name                = secret.value
      identity            = azurerm_user_assigned_identity.jobs.id
      key_vault_secret_id = "${local.kv_uri}secrets/${secret.value}"
    }
  }

  template {
    container {
      name   = "transform"
      image  = var.image
      args   = ["transform"]
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_STORAGE_ACCOUNT"
        value = azurerm_storage_account.lake.name
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.jobs.client_id
      }
      env {
        name        = "TFNSW_API_KEY"
        secret_name = "tfnsw-api-key"
      }
      env {
        name        = "DATABRICKS_HOST"
        secret_name = "databricks-host"
      }
      env {
        name        = "DATABRICKS_HTTP_PATH"
        secret_name = "databricks-http-path"
      }
      env {
        name        = "DATABRICKS_TOKEN"
        secret_name = "databricks-token"
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.jobs_read_secrets,
    azurerm_role_assignment.jobs_write_blobs,
    azurerm_storage_container.raw,
    azurerm_storage_container.extracts,
  ]
}

# ---------------------------------------------------------------- cost guardrail
# Alerts only. The free account's spending limit is what actually stops spend.
resource "azurerm_consumption_budget_subscription" "main" {
  name            = "${var.name_prefix}-budget"
  subscription_id = "/subscriptions/${var.subscription_id}"
  amount          = var.budget_amount
  time_grain      = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00'Z'", timestamp())
  }

  dynamic "notification" {
    for_each = toset([50, 80, 100])
    content {
      enabled        = true
      threshold      = notification.value
      threshold_type = "Actual"
      operator       = "GreaterThan"
      contact_emails = [var.alert_email]
    }
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
