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
- ✅ Silver reconciliation (`ingestion/build_silver.py`, SQL not PySpark — see above):
  dedups RT snapshots to one row per (trip, stop), reconciles against static schedule
  (98.1% direct trip_id match, 56 orphans flagged not dropped), cross-checks TfNSW's
  own published delay value against a plausibility range (0 outliers past 2hr — the
  5,306s max sits inside that range, worth revisiting once more data accumulates)
- ✅ Hand-written SQL Gold tables (`ingestion/build_gold.py`, dbt deferred to Phase 3):
  `dim_date` (30 rows), `dim_route` (137), `dim_stop` (1,214),
  `fact_trip_stop_performance` (2,916 rows), `mart_route_daily_performance`.
  On-time threshold (300s / 5 min) matches TfNSW's own published "Customer On-Time"
  standard, not an arbitrary number — verified via transport.nsw.gov.au, not memory
  (an earlier draft used a misremembered 5:59 threshold, corrected before shipping)
- ✅ One Tableau Public dashboard: [Network Reliability Overview](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/NetworkReliabilityOverview)
  — on-time % by route and avg delay by route, both sorted worst-to-best, built from
  `mart_route_daily_performance.csv`. Published 2026-09-17 as a single-day snapshot
  (no trend line yet — see "one real insight" note above on why)
- ✅ README + PROJECT_PLAN in the repo, basic pytest for the protobuf decode step
- 🟨 The one real insight this phase found, so far: on 2026-09-16, the **STH line
  (CTY_S1c)** ran 0% on-time with a ~39-minute average delay, and the **T2 (IWL_1c)**
  branch also hit 0% on-time — concrete evidence of a real service disruption
  captured live, not a synthetic example. Also found and fixed: TfNSW's v2 feed
  leaves `trip.start_date` empty on every record, requiring a `feed_timestamp`-based
  fallback for `service_date` (see PROJECT_PLAN.md / ingestion/build_silver.py)

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
