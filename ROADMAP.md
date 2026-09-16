# Roadmap — Sydney Transit Intelligence Platform

Living checklist. Update status as work happens; don't let this drift from reality.
Design rationale for each phase lives in [PROJECT_PLAN.md](PROJECT_PLAN.md) — this file
is just the sequencing and status.

Legend: ⬜ not started · 🟨 in progress · ✅ done

---

## Phase 1 — MVP
**Goal:** prove the full path works end-to-end and produces one real, defensible insight.
Scope deliberately narrow: **Sydney Trains only**, GTFS static + trip updates only (no
vehicle positions or alerts yet), 1–2 weeks of captured data.

- ✅ Register on the TfNSW Open Data Hub and generate an API key (account: `maheshsai1204`;
  turns out the personal "API Tokens" key from account settings is what authenticates
  against `api.transport.nsw.gov.au` — no separate "Applications" step needed, resolved
  by testing rather than trusting older/ambiguous docs)
- ✅ Sign up for Databricks Free Edition (workspace live: Serverless Starter Warehouse
  connection details captured in `.env`)
- ✅ Set up a local Python venv (`.venv/`, `requirements.txt` pinned and installed)
- ✅ `ingestion/gtfs_static_ingest.py` — **run live**, pulled a real 10.6MB GTFS bundle
  (agency.txt, routes.txt, stops.txt, trips.txt, stop_times.txt, calendar.txt, etc.)
- ✅ `ingestion/gtfs_rt_ingest.py` — **run live**, decoded 2,870 real trip-stop update
  records across 307 trips. Observed arrival delays ranging 0–5,306 seconds — the
  5,306s (~88 min) outlier is exactly the kind of value the Silver-layer range-check
  (§9 in PROJECT_PLAN) needs to quarantine and investigate, not silently trust
- ✅ Land both into Bronze Delta tables in `workspace.bronze` — **done and verified
  with real row counts**: `gtfs_static_routes` (137), `gtfs_static_stops` (1,214),
  `gtfs_static_trips` (65,916), `gtfs_static_stop_times` (1,208,729),
  `gtfs_static_calendar` (121), `gtfs_rt_trip_updates` (2,916, loaded via `COPY INTO`
  which tracks already-loaded files itself — the actual incremental-loading mechanism,
  see `ingestion/land_bronze.py`)
- ✅ Databricks PAT + SQL warehouse HTTP path added to `.env` (git-ignored, confirmed
  not tracked). Discovered this PAT is scoped to `sql` only — Jobs/Workspace/Files/
  Unity-Catalog-admin APIs all reject it — so Bronze materialization runs as SQL
  (`read_files`/`COPY INTO`) via `ingestion/land_bronze.py`, not a PySpark notebook
  driven by API. See PROJECT_PLAN.md §5 for the full explanation and what this changes
  about orchestration (§11 Jobs get set up by hand in the UI, not provisioned by script)
- ⬜ Silver PySpark notebook: reconcile RT trip_id → static trip_id, compute
  scheduled/actual timestamps and delay_seconds, dedup to latest snapshot per trip-stop
- ⬜ Hand-written SQL Gold tables (dbt deferred to Phase 3): `fact_trip_stop_performance`
  + minimal `dim_route`/`dim_stop`/`dim_date`
- ⬜ One Tableau Public dashboard: Network/Route On-Time Performance Overview
- ⬜ README + PROJECT_PLAN in the repo (done), basic pytest for the protobuf decode step
- ⬜ Write up the one real insight this phase found

## Phase 2 — Data engineering
- ⬜ Formalize ingestion as scheduled Databricks Jobs (Workflows)
- ⬜ Add GTFS-RT vehicle positions + service alerts feeds
- ⬜ Proper Delta Lake structure across all layers (partitioning, schema evolution)
- ⬜ Incremental loading via watermark on `_ingested_at`
- ⬜ Expand scope beyond Sydney Trains to other modes

## Phase 3 — Analytics engineering
- ⬜ Stand up `dbt_transit/` as a real dbt Core project (dbt-databricks adapter)
- ⬜ Rebuild Gold as the full star schema (see docs/data_model.md)
- ⬜ dbt tests: not_null, unique, relationships, accepted_values, custom tests
- ⬜ dbt docs generated and reviewed

## Phase 4 — BI
- ⬜ Build out all 3 Tableau dashboards (Overview, Route/Stop Deep Dive, Service Alerts)
- ⬜ KPI definitions doc + data dictionary
- ⬜ Publish to Tableau Public with screenshots in `tableau/`

## Phase 5 — Production-quality features
- ⬜ GitHub Actions CI: pytest + `dbt build`/`dbt test` on PR against a CI schema
- ⬜ Linting (ruff/black, sqlfluff) in CI
- ⬜ dbt docs published to GitHub Pages
- ⬜ Expand DQ suite + add the Pipeline Health Tableau tab
- ⬜ Small ML delay-risk model (scikit-learn/XGBoost), MLflow-logged
- ⬜ Architecture diagram + runbook in `docs/`
- ⬜ *(stretch, optional)* Structured Streaming/Auto Loader for RT ingestion

---

## Explicitly out of scope (see PROJECT_PLAN §17 for why)

Airflow/Dagster, Kafka/streaming infra, a custom web frontend, multi-cloud, deep
learning or model serving, full historical depth across all 4 modes in the MVP,
hand-rolled GTFS parsers, a custom orchestrator.
