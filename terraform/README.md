# Azure infrastructure (Terraform)

Defines the Azure side of the pipeline: storage (ADLS Gen2) for the raw archive and extracts, Key Vault,
a managed identity, Log Analytics, a Container Apps environment, the two scheduled jobs, and a budget.
Plan and context: [docs/azure_extension_plan.md](../docs/azure_extension_plan.md).

## Two-stage apply (so secrets never enter Terraform state)

```bash
cd terraform
az login
export TF_VAR_subscription_id="$(az account show --query id -o tsv)"
export TF_VAR_alert_email="you@example.com"          # never committed

terraform init
terraform apply                                       # stage 1: foundation only (deploy_jobs=false)

# Load the four secrets once with the CLI (values from your local .env), not through Terraform:
KV="$(terraform output -raw key_vault)"
az keyvault secret set --vault-name "$KV" --name tfnsw-api-key        --value "$TFNSW_API_KEY"
az keyvault secret set --vault-name "$KV" --name databricks-host      --value "$DATABRICKS_HOST"
az keyvault secret set --vault-name "$KV" --name databricks-http-path --value "$DATABRICKS_HTTP_PATH"
az keyvault secret set --vault-name "$KV" --name databricks-token     --value "$DATABRICKS_TOKEN"

terraform apply -var deploy_jobs=true                 # stage 2: the scheduled jobs
```

## Teardown

```bash
terraform destroy -var deploy_jobs=true
```

Key Vault soft-delete keeps the vault name reserved for 7 days after a destroy; that is expected.

## Cost

Nothing here is free-tier-only; everything runs inside the Azure free account's credit, with its spending
limit as the hard stop. The budget (variable `budget_amount`) only sends email alerts. See the plan for
the cost model and the kill switch.
