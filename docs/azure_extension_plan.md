# Azure extension plan

Status (2026-11-05): Phase 0 is built and tested on the `azure-extension` branch. **Nothing is deployed and no Azure account exists yet.**

## 0. Goal and rules

Extend the existing project with real Azure services so it runs without the laptop, and so the resume can say
"deployed on Azure" truthfully. Rules:

1. **Extend, don't rebuild.** Databricks Free Edition, dbt, the Gold model, CI and Tableau stay exactly as they are.
2. **Total spend: $0.** Everything lives inside the free account's $200 credit, with a hard stop and a teardown.
3. **Reversible at every step.** The laptop job (launchd) stays available until the Azure job has proven itself.
4. **Only claim what is deployed and verified.**

## 1. What the research verified, and what it did not

Read from Microsoft and Databricks pages on 2026-11-05.

| Verified | Source |
|---|---|
| Free account: $200 credit, up to 30 days. Spending limit is **on by default** and cannot be changed; when it is reached, deployed resources are disabled or removed. | azure free page, spending-limit doc |
| After 30 days or when the credit is spent you must move to pay-as-you-go or services are disabled. **Pay-as-you-go has no spending limit.** | same |
| The spending limit does not stop every charge (marketplace items, support plans, Entra P1/P2 bill separately). | spending-limit doc |
| Card and phone needed to sign up (temporary $1 authorization). One free account per new customer. | free page |
| Container Apps free grant: 180,000 vCPU-s, 360,000 GiB-s, 2M requests per subscription per month. | pricing page |
| Functions free grant: 1M requests + 400,000 GB-s (Consumption, legacy); 250,000 executions + 100,000 GB-s (Flex). | pricing page |
| Azure Monitor: first 5 GB/month of analytics logs free. Azure DevOps: 5 users free. | monitor pricing |
| Azure Container Registry is **not** free. | ACR pricing |
| **Azure Databricks free trial (14 days) requires a pay-as-you-go subscription with the spending limit removed**, plus a vCPU quota request. VM/compute is charged separately. | Microsoft Learn free-trial page |
| Databricks Free Edition: serverless only, one 2X-Small SQL warehouse, max 5 concurrent job tasks, non-commercial use, fair-use shutdown. | Databricks docs |

| NOT verified (treat as unknown until measured) | How the plan handles it |
|---|---|
| Per-unit prices (every price loaded as "$-") | Phase 0 builds a cost model in the Azure Pricing Calculator, region Australia East |
| Whether cron Container Apps Jobs draw on the free grant | Credit covers it either way; measured in Phase 3 |
| Free allowance for Key Vault and storage (none listed) | Assumed cents; measured daily |
| Pulling a public `ghcr.io` image into Container Apps | Tested in Phase 0 and Phase 2 |
| Whether Free Edition can read Azure storage | Not relied on; see architecture |

## 2. The zero-cost strategy (two consequences of the research)

**A. The 30-day clock.** The credit expires 30 days after sign-up. So **do not create the account until all code
is ready** (Phase 0, offline and free). Then use the 30 days for deploying, proving and collecting evidence,
and tear everything down before day 30. **Never upgrade to pay-as-you-go**: that removes the spending limit,
which is the safety net.

**B. Azure Databricks is not in the zero-cost core.** Its trial needs a pay-as-you-go subscription with the
spending limit removed, so it cannot be guaranteed free. Databricks Free Edition stays the compute. Azure
Databricks is an optional stretch (Phase 9) only if you knowingly accept a small, capped cost.

## 2b. A finding that changed the design (2026-11-05)

While preparing Phase 0 I found the live pipeline had been failing on every run since **3 Nov 2026 00:05 UTC**
(36 consecutive failed runs): Databricks refused to start the SQL warehouse (`BAD_REQUEST: Cannot create the
resource`; the warehouse state was `STOPPED`). That is consistent with the Free Edition fair-use quota, which says
compute is shut down for the rest of the day, or in extreme cases the rest of the month. The laptop schedule opened
a SQL session every 15 minutes and ran a full dbt build every 15 minutes, which kept the warehouse awake around the
clock.

Moving the same schedule to Azure would not fix that. So **Azure storage becomes the buffer**: ingestion only writes
to ADLS (no Databricks session at all), and an hourly job pushes whatever is new to Databricks in one short session.
This also means an outage can no longer lose data: the sync step uploads anything missing from the volume.

## 3. Target architecture

```
Azure Container Apps Job "ingest"    every 15 min   TfNSW API -> Parquet -> ADLS Gen2 (raw archive). No Databricks session.
Azure Container Apps Job "transform" hourly         static timetable refresh (daily) -> sync new files ADLS -> Databricks volume
                                                    -> land Bronze -> dbt build -> health check -> extracts to ADLS
Key Vault        TfNSW key, Databricks host/token/path (read through a managed identity, no secrets in code)
ADLS Gen2        containers: raw/ (every poll + timetable zips), extracts/ (Tableau CSVs)
Log Analytics    job logs (30-day retention), Azure Monitor alert on failed executions -> email
Terraform        everything above as code; GitHub Actions deploys through OIDC (no stored Azure secrets)
ghcr.io          the container image (free, public); no Azure Container Registry
UNCHANGED        Databricks Free Edition (Bronze/Silver/Gold), dbt project and tests, 3 existing workflows, Tableau
```

Why two jobs: ingestion is short and frequent; the dbt build is longer and only needs to run hourly (this also
halves the load on the Free Edition warehouse that caused 429 errors before).

## 4. Phases, with exit criteria

| Phase | When | What | Exit criteria |
|---|---|---|---|
| **0. Offline preparation** | before the clock starts (3 to 5 evenings) | Install Terraform and Azure CLI (free). Code changes (section 5). Dockerfile. Terraform modules (`validate` only, no apply). GitHub Actions to build the image. Cost model. | Tests green; image runs locally against real Databricks; Azurite storage tests pass; `terraform validate` passes; cost model written |
| **1. Account and guardrails** | Day 0 | You sign up (card, phone, MFA). Confirm the spending limit is on. Budget with alerts at 50/80/100%. OIDC trust for GitHub. | Portal shows $200 credit and spending limit on |
| **2. Foundation** | Day 1 to 2 | `terraform apply`: resource group (Australia East), storage, Key Vault, Log Analytics, Container Apps environment, managed identity | All resources present; Cost Management shows about $0 after 24 h |
| **3. Shadow ingest** | Day 2 to 5 | `ingest` job runs every 15 min writing **only to ADLS** while the laptop pipeline keeps running everything | 48 h of runs; success 99% or better; record counts match the local files; daily cost matches the model |
| **4. Cutover** | Day 5 to 7 | Pause launchd. Turn on the hourly `transform` job, which syncs the archive into Databricks. | 3 consecutive successful transform runs; Databricks Query History shows the Azure job; rollback tested |
| **5. Hardening** | Day 7 to 10 | Failure alert by email, least-privilege review, `terraform plan` on pull requests, guarded `destroy` workflow, resource tags | A deliberate failure (bad token) triggers the alert; fixed and re-verified |
| **6. Operate and evidence** | Day 10 to 24 | Let it run. Record runs, success rate, daily cost, data collected. Take portal screenshots. Update README, docs, walkthrough, resume. | 10+ days of runs; evidence pack complete |
| **7. Teardown** | Day 25 to 26 | Export cost report and logs, final screenshots, `terraform destroy`, confirm the subscription is empty. **Do not upgrade.** Reload launchd. | `az resource list` is empty; credit left over shown |
| **8. Optional: free scheduling afterwards** | after teardown | Run `transform` hourly from a GitHub Actions schedule (free for public repos) | Scheduled workflow green |
| **9. Optional: Azure Databricks stretch** | only with your explicit approval | Needs pay-as-you-go (no spending limit). Small, capped, destroyed the same day. | Separate budget agreed first |

Kill switch: if the credit used passes $25 by day 7, or any unexpected charge appears, run `terraform destroy`.

## 5. Code changes (all in the existing repo)

Built and tested on the branch (42 tests, plus the storage code run against the Azurite emulator; the ingest job
also ran inside the container against the live TfNSW API):

| Change | Why |
|---|---|
| New `ingestion/azure_storage.py` (upload via `azure-storage-blob` and `azure-identity`) | Archive every poll and timetable zip to ADLS |
| Static timetable versions read from the Databricks volume (`LIST`) instead of local `data/` | A container's disk is wiped on every run; `land_bronze.all_static_zips()` reads local files today |
| Two entry points: `ingest` and `transform` | Replace `scripts/run_pipeline.sh` and launchd inside the container (the shell script stays for local use) |
| `Dockerfile` (slim Python, non-root, dbt and its packages) | One image for both jobs |
| Extract export writes to ADLS `extracts/` when running in Azure | No laptop folder in the cloud |
| Tests with the Azurite storage emulator | Cloud code tested without an account |
| `terraform/` folder and a deploy workflow | Infrastructure as code, deployed through OIDC |
| `docs/azure.md`, README section, architecture diagram, runbook additions | Documentation and proof |

## 6. Cost model (estimates, to be measured)

Rough compute use per month, from the current run lengths (about 40 s for ingest, about 5 min for transform):

- `ingest`, 0.25 vCPU, 2,880 runs: about 29,000 vCPU-s (16% of the grant).
- `transform`, 0.5 vCPU hourly, 720 runs: about 108,000 vCPU-s (60% of the grant).

If cron jobs count against the free grant, this fits. If not, the credit pays; expected total is a few dollars at
most. Real numbers come from Cost Management on days 1, 3 and 7. Run transform every 2 hours if usage is high.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Spending limit reached, services disabled | Budget alerts, daily cost check, kill switch |
| Accidentally upgrading to pay-as-you-go | Never click Upgrade; no marketplace items, no support plan |
| Free Edition quota or 429s when two schedulers overlap | Pause launchd before cutover; hourly dbt |
| Free Edition is non-commercial and quota-limited | Portfolio use only; documented |
| `ghcr.io` pull fails | Tested early; fall back to Container Apps secrets with a public Docker Hub image |
| Credential exposure again | Key Vault, managed identity, OIDC; nothing in the repo; secret scan before every push |
| Data in ADLS lost at teardown | Download a copy first; it is small |
| Sign-up rejected (card, one per person) | Azure for Students is an alternative if still eligible (not stated for recent graduates) |

## 8. What the resume can truthfully say, and when

After phase 6, with evidence: "Deployed the pipeline on Azure (Container Apps Jobs, ADLS Gen2, Key Vault,
managed identity, Azure Monitor) with Terraform and GitHub Actions OIDC; operated 24/7 for N days (X runs, Y%
success) within the free credit." Skills to add: Azure Container Apps, ADLS Gen2, Key Vault, Managed Identity,
Azure Monitor, Terraform, Docker. Do not claim "Azure Databricks" unless phase 9 happens.

## 8b. Phase 0 progress

| Item | State |
|---|---|
| Azure archive step in all ingest scripts (`landing.py`, `azure_storage.py`) | Done, tested against Azurite |
| Timetable versions read from the Databricks volume (`land_bronze.py`) | Done, unit-tested with a scripted cursor; **not yet run against real Databricks (it is down)** |
| Idempotent `sync_to_volume.py` | Done, unit-tested; same caveat |
| `ingest` and `transform` job entry points (`jobs.py`) | Done; `ingest` run in the container against the live API |
| Dockerfile (non-root, no secrets, allow-list `.dockerignore`) | Built and inspected locally (1.08 GB) |
| Terraform (storage, Key Vault, identity, Log Analytics, Container Apps jobs, budget) | `terraform validate` passes; never planned (needs an Azure login) |
| Workflows: image build to GHCR, Terraform CI, CI with Azurite | Written; run by GitHub once the branch is pushed |
| Real end-to-end test of `transform` against Databricks | Blocked until Databricks accepts sessions again |

## 9. Decisions needed

1. ~~Approve the plan and start Phase 0~~ Done: approved 2026-11-05.
2. ~~Terraform or Bicep~~ Terraform, with the Azure CLI.
3. ~~Alert email~~ Provided; passed as a deploy-time variable, never committed.
4. Whether Phase 9 (Azure Databricks, small capped cost) is ever wanted. Default: no.
5. Before Phase 1: Databricks must be reachable again (check the workspace; see section 2b), so the cutover can be tested for real.
