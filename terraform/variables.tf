variable "subscription_id" {
  description = "Azure subscription ID (az account show --query id -o tsv)."
  type        = string
}

variable "location" {
  description = "Azure region. Australia East is Sydney."
  type        = string
  default     = "australiaeast"
}

variable "name_prefix" {
  description = "Short prefix for resource names (lowercase letters and digits)."
  type        = string
  default     = "sydtransit"
}

variable "image" {
  description = "Container image for both jobs (public, so no Azure registry is needed)."
  type        = string
  default     = "ghcr.io/mskandula/sydney-transit-pipeline:latest"
}

variable "alert_email" {
  description = "Where budget alerts are sent. Pass it at apply time (TF_VAR_alert_email) so it never lives in the repo."
  type        = string
  sensitive   = true
}

variable "budget_amount" {
  description = "Monthly budget in the subscription's billing currency. Alerts only; the free account's spending limit is the hard stop."
  type        = number
  default     = 10
}

variable "deploy_jobs" {
  description = "Stage 2: create the scheduled jobs. Leave false until the Key Vault secrets exist (see terraform/README.md)."
  type        = bool
  default     = false
}

variable "ingest_cron" {
  description = "Schedule for the ingest job (UTC cron)."
  type        = string
  default     = "*/15 * * * *"
}

variable "transform_cron" {
  description = "Schedule for the transform job (UTC cron). Hourly keeps Databricks Free Edition usage low."
  type        = string
  default     = "5 * * * *"
}
