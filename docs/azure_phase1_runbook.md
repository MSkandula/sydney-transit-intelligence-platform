# Azure sign-up and guardrails (Phase 1)

Do this only when Phase 0 is finished and merged: **the 30-day free-credit clock starts at sign-up**.
Context and cost model: [azure_extension_plan.md](azure_extension_plan.md).

## 1. Sign up (you do this; nobody else should type your card or phone details)

1. Go to https://azure.microsoft.com/free and choose **Start free**. Sign in with a personal Microsoft account.
2. Enter a phone number and a card. Azure may place a temporary $1 authorization; the free account does not charge the card.
3. Pick the **Azure free account** (not Pay-as-you-go).
4. When the portal opens, go to **Subscriptions**, open your subscription, and confirm the offer is "Free Trial" with about $200 of credit.

## 2. The three things that could cost money (read before clicking anything)

| Do not | Why |
|---|---|
| Click **Upgrade** or switch to Pay-as-you-go | It removes the spending limit, which is the hard stop. Microsoft's docs: the spending limit is on by default for the free account, cannot be changed, and is lifted by upgrading. |
| Buy marketplace items, a support plan, or Entra P1/P2 | Microsoft's docs say the spending limit does not stop these. |
| Create anything outside the Terraform-managed resource group | Untracked resources are easy to forget at teardown. |

## 3. Verify the guardrails (I run these; paste nothing sensitive)

```bash
az login
az account show --query "{name:name, state:state, id:id}" -o table
az account list-locations --query "[?name=='australiaeast'].displayName" -o tsv
```

Expected: state `Enabled`, offer free trial, region Australia East available.

In the portal, **Cost Management + Billing** should show the credit remaining and the spending limit **On**.
A screenshot of that page goes in the evidence pack.

## 4. Budget alert

Created by Terraform (`azurerm_consumption_budget_subscription`): email alerts at 50%, 80% and 100% of the budget.
This is an alert, not a stop. The spending limit is the stop.

## 5. Day-30 rule

Before day 25: export the evidence, run `terraform destroy`, confirm the subscription is empty. After day 30 the
free account is disabled unless upgraded. Do not upgrade.

## 6. If anything looks wrong

Run `terraform destroy -var deploy_jobs=true` first, ask questions second.
