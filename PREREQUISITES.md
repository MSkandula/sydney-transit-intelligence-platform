# Prerequisites — what's needed before Phase 1 build starts

Checked against this Mac on 2026-09-16. Update the checkboxes as each is done.

## Accounts to create (all free, no card required)

- ⬜ **TfNSW Open Data Hub** — https://opendata.transport.nsw.gov.au/
  Register, then create an "application" to get an API key (personal/portfolio use is
  fine to state as the purpose). Needed for both GTFS static and GTFS-RT access.
- ⬜ **Databricks Free Edition** — sign up via https://login.databricks.com/ (choose
  Free Edition, not a trial). No company email or credit card needed. This is where
  all Bronze/Silver/Gold compute and storage lives.
- ✅ **GitHub** — already have `github.com/MSkandula` (from your resume). We'll create
  a new repo for this project when you're ready to push — I'll ask before doing that,
  since publishing anything is your call, not mine.
- ✅ **Tableau Public** — already installed on this Mac (`Tableau Public.app`).

## Local tooling — already present on this Mac, nothing to install

- ✅ Python 3.12.7 (via Anaconda)
- ✅ Git 2.50.1, already configured with your email
- ✅ Homebrew
- ✅ Tableau Public + Tableau Desktop

## Local tooling — optional, your call

- ⬜ **VS Code** — found in `~/Downloads/Visual Studio Code.app` but not moved to
  `/Applications`. Say the word and I'll move it, or you can drag it over yourself.
- ⬜ **GitHub CLI (`gh`)** — not installed. Not required (the GitHub website covers
  everything), but convenient for PRs/CI from the terminal. `brew install gh` if wanted.

## What I'll set up as part of the build (no action needed from you)

- Project-local Python virtual environment (not the base Anaconda env) — matches the
  `.venv` convention already used in your other Desktop projects.
- `.env` file for the TfNSW API key and Databricks host/token — **you'll paste your own
  keys into it once generated; I won't ask you to send them to me in chat**, and it's
  already excluded via `.gitignore` so it never gets committed.
- `dbt_transit/profiles.yml` pointing at the Free Edition Serverless Starter Warehouse.

## Before I start Phase 1 build work, I need from you

1. Confirmation you've registered on the TfNSW Open Data Hub and generated an API key
   (or say the word and I'll walk you through that registration step by step).
2. Confirmation you've signed up for Databricks Free Edition (same offer above).
3. A yes/no on moving VS Code + installing `gh` (both optional, low-stakes).

Everything else — repo structure, ingestion scripts, PySpark, dbt project, dashboards —
I can build once those two accounts exist.
