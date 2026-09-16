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

- ⬜ Register for a TfNSW Open Data Hub API key
- ⬜ Verify Databricks Free Edition specifics: job scheduling frequency, external
  network access from notebooks, storage limits (see PROJECT_PLAN §5 "known unknown")
- ⬜ `ingestion/gtfs_static_ingest.py` — pull + store one static feed snapshot
- ⬜ `ingestion/gtfs_rt_ingest.py` — poll trip updates, decode protobuf, store snapshot
- ⬜ Land both into Bronze Delta tables (manual run is fine for MVP — no scheduling yet)
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
