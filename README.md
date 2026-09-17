# Sydney Transit Intelligence Platform

An analytics platform that ingests live public transport data from Transport for
NSW (TfNSW) to measure, explain, and surface where Sydney's rail network is
underperforming — and why.

## The problem

TfNSW publishes a live GTFS-Realtime feed, but not a consolidated, historical,
analysis-ready reliability dataset — the realtime feed is a snapshot that only
becomes useful for trend analysis once it's captured over time and reconciled
against the published schedule. That reconciliation (which trip was late, by how
much, and what else was happening at the time) is the actual problem this project
solves.

## Why this project

My other projects — [PAYscope](https://github.com/MSkandula) and E-Commerce
Delivery & Retention Analysis — prove SQL, Python, Power BI/DAX, Tableau, and
data-quality thinking on static, already-collected datasets. This one is built to
demonstrate what those don't: live API ingestion, a lakehouse (Bronze/Silver/Gold),
incremental loading, and pipeline-level data quality checks — the skills that
separate a Data Analyst portfolio from one that also stands up for Junior Data
Engineer / Analytics Engineer roles in the Sydney market. It uses a real, public,
Sydney-specific data source instead of a generic dataset.

## Architecture

```
TfNSW Open Data Hub (GTFS static + GTFS-Realtime v2)
        │
        ▼
Python ingestion  ──────────────►  local landing (data/, git-ignored)
        │
        ▼
Databricks Unity Catalog volume (workspace.bronze.raw_landing)
        │
        ▼
BRONZE   Delta tables — read_files() for static, COPY INTO for realtime
        ▼                (COPY INTO tracks already-loaded files itself —
SILVER   Delta tables —  that's the incremental-loading mechanism, not a
         dedup + schedule  manual reimplementation of one)
         reconciliation
        ▼
GOLD     star schema — dim_date / dim_route / dim_stop /
         fact_trip_stop_performance / mart_route_daily_performance
        │
        ▼
CSV extracts  ──────────────►  Tableau Public dashboards
```

Everything runs on free tooling: Databricks Free Edition (serverless SQL
warehouse + Unity Catalog), GitHub Actions, and Tableau Public. No paid cloud
services anywhere in the stack.

## Tech stack

| Layer | Tool | Why |
|---|---|---|
| Ingestion | Python (`requests`, `gtfs-realtime-bindings`) | Pulls GTFS static + realtime (protobuf) feeds from TfNSW's Open Data Hub |
| Storage / compute | Databricks Free Edition, Delta Lake | Free serverless lakehouse; ACID tables; handles schema drift across weekly static releases |
| Bronze → Gold transforms | SQL via the Databricks SQL warehouse (`read_files()`, `COPY INTO`) | This project's access token is scoped to SQL only — confirmed by testing, not assumed — so Bronze/Silver/Gold run as SQL rather than PySpark notebooks driven by API |
| Transformation (Phase 3) | dbt Core (dbt-databricks adapter) | Same Gold layer, rebuilt with tests, docs, and incremental models |
| BI | Tableau Public | Operational dashboards published from Gold-layer extracts |
| CI/CD (Phase 5) | GitHub Actions | Lint + unit tests, `dbt build` against a CI schema on every PR |
| ML (Phase 5, secondary) | scikit-learn / XGBoost | Small delay-risk classifier — not the focus |

Full design rationale, including two things discovered only by actually building
this (the token's SQL-only scope, and TfNSW's realtime feed leaving `start_date`
blank) live in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## What's built and verified so far

Not a plan — real output from the live pipeline:

- **Bronze**: 6 Delta tables in `workspace.bronze` — 137 routes, 1,214 stops, 65,916
  trips, 1,208,729 scheduled stop-times, 2,916 realtime trip-stop updates
- **Silver**: 98.1% of realtime records reconcile directly against the static
  schedule on `trip_id`; the rest are flagged as orphans, not dropped
- **Gold**: a working star schema, using TfNSW's actual published on-time standard
  (within 5 minutes) rather than an arbitrary threshold
- **A real finding**: on 2026-09-16, Sydney Trains' STH line ran 0% on-time with a
  ~39-minute average delay — captured live, not a synthetic example
- **5 passing unit tests** on the GTFS-Realtime protobuf decode logic
- **Live dashboard**: [Network Reliability Overview on Tableau Public](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/NetworkReliabilityOverview) — on-time % and average delay by route, sorted worst to best

See [ROADMAP.md](ROADMAP.md) for the full, currently-accurate status per phase.

## Business impact

The point of this platform isn't just "here's a dashboard" — it's answering the
question a network performance team would actually ask: **where should limited
operational attention go first?** `gold.mart_line_delay_concentration` answers that
directly, using the same concentration framing as the "top 10% of sellers drive
67.6% of revenue" finding in my E-Commerce project:

> **3 of Sydney Trains' 16 lines (STH, T4, SCO) are responsible for 50.5% of all
> network delay-minutes captured so far. 6 lines account for 79.0%.**
> (as of 2026-09-17, across 7,399 trip-stop observations spanning 2 days —
> this number updates as the scheduled pipeline accumulates more history)

That's a concrete, actionable answer — fix or investigate those lines first, not
spread effort evenly across 16 — and it's recomputed automatically every time the
pipeline runs, so it gets more statistically reliable as more history accumulates
(see [scripts/run_pipeline.sh](scripts/run_pipeline.sh), which polls TfNSW every 15
minutes to build that history up over time).

**Second finding — do disruption alerts actually matter, or is impact overstated?**
`gold.mart_alert_delay_impact` (from the new `gtfs_service_alerts` feed, joined
against actual observed delay during each alert's active window) answers this with
real correlation, not assumption:

> **The "Buses replace trains between Leppington and Fairfield" maintenance alert
> correlates with an 11.5-minute average delay increase on route IWL_1c while
> active, versus that route's own baseline.**

That's the difference between "we posted a disruption notice" and "the disruption
notice's operational impact was actually this large" — the kind of answer that
turns a dashboard into an evaluation of communication effectiveness, not just a
delay tracker.

## Repository structure

```
ingestion/          Python: TfNSW ingestion, Databricks volume upload, Bronze/
                     Silver/Gold SQL builders, Tableau extract export
scripts/            run_pipeline.sh — the scheduled ingestion entry point
notebooks/           Optional PySpark path for working directly in the Databricks
                     UI (unexecuted — Phase 1 runs entirely via ingestion/)
dbt_transit/         dbt project scaffold — models arrive in Phase 3
tableau/extracts/    Gold-layer CSVs, ready for Tableau Public
tests/               pytest unit tests
docs/data_model.md   Star schema reference — grain, keys, columns
docs/scheduled_ingestion.md  How the local launchd job works, and its real limits
.github/workflows/   CI/CD (Phase 5)
PROJECT_PLAN.md      Full design doc: business case → interview prep
ROADMAP.md           Phased build plan and live status
PREREQUISITES.md     Accounts/tools needed to run this yourself
```

## Running this yourself

See [PREREQUISITES.md](PREREQUISITES.md) for the accounts needed (TfNSW API key,
Databricks Free Edition), then:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own keys — never commit this file

python ingestion/gtfs_static_ingest.py
python ingestion/gtfs_rt_ingest.py
python ingestion/land_bronze.py
python ingestion/build_silver.py
python ingestion/build_gold.py
python ingestion/export_gold_extracts.py
```
