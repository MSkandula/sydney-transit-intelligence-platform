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
  `fact_trip_stop_performance` (2,916 rows), `mart_route_daily_performance`,
  `mart_line_delay_concentration` (the business-impact mart — see README.md).
  On-time threshold (300s / 5 min) matches TfNSW's own published "Customer On-Time"
  standard, not an arbitrary number — verified via transport.nsw.gov.au, not memory
  (an earlier draft used a misremembered 5:59 threshold, corrected before shipping)
- ✅ Two Tableau Public dashboards, same workbook:
  1. [Network Reliability Overview](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/NetworkReliabilityOverview)
     — on-time % by route and avg delay by route, both sorted worst-to-best, built
     from `mart_route_daily_performance.csv`
  2. [Business Impact](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/BusinessImpact)
     — a proper Pareto chart (bars + cumulative % line, dual axis) for
     `mart_line_delay_concentration`, and a diverging bar chart for
     `mart_alert_delay_impact`. Both built collaboratively — real trial and error
     worth noting: a field landing on the wrong shelf (Columns instead of Rows),
     color encoding defaulting to discrete instead of continuous (fixed by
     Option-dragging the already-continuous pill instead of a fresh one from the
     Data pane), and a reversed diverging color scale twice, once per chart.
- ✅ README + PROJECT_PLAN in the repo, basic pytest for the protobuf decode step
- ✅ Real insights this phase found:
  1. On 2026-09-16, the **STH line (CTY_S1c)** ran 0% on-time with a ~39-minute
     average delay, and the **T2 (IWL_1c)** branch also hit 0% on-time — a real
     service disruption captured live, not a synthetic example.
  2. **Business-impact headline** (`gold.mart_line_delay_concentration`): 3 of 16
     lines (STH, SHL, SCO) account for 60.8% of all network delay-minutes; 5 lines
     account for 81%. A concrete "fix these first" answer, not just a dashboard.
  3. Also found and fixed: TfNSW's v2 feed leaves `trip.start_date` empty on every
     record, requiring a `feed_timestamp`-based fallback for `service_date` (see
     PROJECT_PLAN.md / `ingestion/build_silver.py`).

## Phase 2 — Data engineering
- ✅ **Real bug caught by the scheduled job's first run, fixed same-day**: Silver's
  dedup window was `PARTITION BY trip_id, stop_id, stop_sequence` — correct with one
  day of data, silently wrong with two. Sydney Trains reuses `trip_id` across
  different calendar days, so the moment a second day's snapshot landed, 188
  trip-stops from 2026-09-16 got silently collapsed into 2026-09-17's rows (Silver
  showed 6,544 rows against Bronze's 6,732 — a mismatch that shouldn't exist since
  Silver only dedups, it doesn't drop legitimate rows). Fixed by adding
  `service_date` to the partition key (`ingestion/build_silver.py`). This is exactly
  why the scheduled job was worth building *before* moving on to more features — a
  single-snapshot pipeline can never surface a bug that only exists across days.
- ✅ Formalize ingestion as scheduled — pulled forward from Phase 2 into Phase 1 once
  it became clear accumulated history (not a single snapshot) is what a real trend/
  business-impact story needs. Running as a **local launchd job**
  (`scripts/run_pipeline.sh` + `~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist`,
  every 15 min), not Databricks Jobs — the project's PAT can't drive the Jobs API
  (see §5 in PROJECT_PLAN), and launchd only runs while the Mac is awake, so this
  isn't a true 24/7 scheduler. Full Databricks Workflows setup (by hand, in the UI)
  remains the honest Phase 2 target if 24/7 coverage is worth the manual setup later.
- ✅ Add GTFS-RT service alerts feed (`ingestion/gtfs_alerts_ingest.py`,
  `v2/gtfs/alerts/sydneytrains`) — 1,160 real alert-entity records landed live,
  genuine human-readable content ("Buses replace trains between Leppington and
  Fairfield"). Unlocked `gold.mart_alert_delay_impact` (see README.md's second
  business-impact finding: an 11.5-minute measured delay lift during one alert's
  active window). Vehicle positions still not started — lower business value than
  alerts for the "why is it late" question, deprioritized accordingly.
  - **Real bug hit and fixed same-day**: the first `COPY INTO` failed with
    `DELTA_FAILED_TO_MERGE_FIELDS` on `trip_id` — this feed has zero trip-level
    alerts so far, so pandas inferred the always-null `trip_id` column as a
    non-string dtype, conflicting with the Delta table's declared schema the moment
    a differently-typed file landed. Fixed by explicitly casting nullable string
    columns before writing Parquet (`ingestion/gtfs_alerts_ingest.py`). A second,
    unrelated issue in the same debugging session: a manual run and the scheduled
    launchd run overlapped and both hit Databricks' `RESOURCE_EXHAUSTED` (429) on
    the staging API — expected under concurrent load, not investigated further
    since it resolved on retry, but worth knowing before assuming two failures are
    the same root cause.
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
