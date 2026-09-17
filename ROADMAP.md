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
- ✅ Stood up `dbt_transit/` as a real dbt Core project (dbt-databricks adapter) —
  8 staging models + sources.yml, 1 intermediate model (the Silver reconciliation
  logic, ported from `build_silver.py`), 8 marts (dims, incremental fact, both
  business-impact marts). Clean `dbt build`: **46 passed, 0 errors** against live data.
- ✅ Rebuilt Gold as the full star schema, now dbt-managed — see docs/data_model.md
- ✅ 31 dbt tests: not_null, unique, relationships (some `severity: warn` where a
  real, expected mismatch exists — e.g. alerts referencing routes outside the
  current static feed), accepted_values, and `dbt_utils.unique_combination_of_columns`
  / `accepted_range` from the dbt_utils package
- ✅ dbt docs generated (`dbt docs generate`, verified locally) — publishing to
  GitHub Pages is a Phase 5 CI item, not done yet
- ✅ **Cut the scheduled pipeline over to dbt** — `scripts/run_pipeline.sh` now runs
  `dbt build` instead of `ingestion/build_silver.py` + `build_gold.py`, which are
  kept in the repo as the superseded Phase 1 reference (see dbt_transit/README.md
  for why running both would conflict — it did, once, during the actual cutover)
- ✅ **Three real things this dbt project caught on its first build against real
  data** (full detail in dbt_transit/README.md):
  1. An `accepted_values` test failed — TfNSW uses a `REPLACEMENT` schedule_relationship
     value (bus-replaces-train services) that wasn't in the initial accepted list,
     written from general GTFS-RT spec knowledge rather than the real feed.
  2. A uniqueness test failed with 1,348 violations — TfNSW reports
     `stop_sequence=0` for every stop on at least some NSW TrainLink intercity
     trips, breaking the assumption (also baked into PROJECT_PLAN.md §10's original
     spec) that `stop_sequence` alone is unique per trip. Fixed by adding `stop_id`
     to the fact table's grain — corrected in PROJECT_PLAN.md and data_model.md too.
  3. dbt's incremental `MERGE` failed with `DELTA_MERGE_UNRESOLVED_EXPRESSION`
     against the pre-existing hand-SQL `gold.fact_trip_stop_performance` table
     (different, incompatible column set). Fixed by dropping the legacy table —
     the intended outcome of the cutover, not a workaround.

## Phase 4 — BI
- ✅ 2 of 3 planned dashboards published to Tableau Public with screenshots in
  `tableau/screenshots/` (fetched from Tableau's own auto-generated preview
  thumbnails — the embedded JS viz doesn't render in an automated browser, a
  bot-detection issue on Tableau's end):
  - [Network Reliability Overview](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/NetworkReliabilityOverview) —
    on-time % and avg delay by route
  - [Business Impact](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/BusinessImpact) —
    Pareto (delay concentration) + alert-delay-impact charts
  - Route & Stop Deep Dive and a dedicated Service Alerts dashboard remain — the
    alert data now backing them (`fact_service_alerts`, `mart_alert_delay_impact`)
    already exists via dbt, so this is mostly a Tableau-building session, not new
    data engineering
- ✅ KPI definitions doc: [docs/kpi_definitions.md](../docs/kpi_definitions.md) —
  precise definition of every metric used across the dashboards and the
  business-impact findings, including the deliberate design choices behind each
  one (e.g. why orphan trips are flagged not filtered, why delay concentration
  uses positive delay only)

## Phase 5 — Production-quality features
- ✅ GitHub Actions CI:
  - [.github/workflows/ci.yml](../.github/workflows/ci.yml) — ruff + pytest on
    every push/PR
  - [.github/workflows/dbt-ci.yml](../.github/workflows/dbt-ci.yml) — `dbt build`
    on every push/PR touching `dbt_transit/**`, against a dedicated `ci` schema on
    the same Databricks warehouse (verified locally before trusting it in CI: had
    to fix `generate_schema_name.sql` first, since the custom-schema macro would
    otherwise have made `--target ci` write into the same schemas as dev — see the
    macro's own comment for why)
  - Databricks credentials added as GitHub Actions repo secrets
    (`DATABRICKS_HOST`/`TOKEN`/`HTTP_PATH`)
- ✅ Linting: ruff (`pyproject.toml`) — 7 pre-existing issues found and fixed
  (unused import, unsorted imports) before wiring it into CI, so CI starts green.
  sqlfluff for dbt SQL not added — ruff + dbt's own tests cover most of the value
  sqlfluff would add here, and this project's SQL is not large enough yet to
  justify a second linter with its own config to maintain
  Both workflows verified passing on GitHub's actual infrastructure on the first
  real push (not just locally) — `gh run watch` confirmed both green, including a
  live GitHub Actions → Databricks connection for the dbt build.
- ✅ **dbt docs → GitHub Pages — live**:
  [mskandula.github.io/sydney-transit-intelligence-platform](https://mskandula.github.io/sydney-transit-intelligence-platform/).
  Was blocked on a real, confirmed constraint (GitHub Pages for private repos
  needs a paid plan — `422 Your current plan does not support GitHub Pages for
  this repository`, not assumed), unblocked once the repo went public.
  [.github/workflows/dbt-docs.yml](../.github/workflows/dbt-docs.yml) runs `dbt
  docs generate` (read-only against the live warehouse — describes schema, issues
  no DDL/DML) and deploys via `actions/deploy-pages` on every push to main
  touching `dbt_transit/**`. Verified live: catalog data populated correctly (real
  row counts, e.g. `fact_trip_stop_performance` showing 22,916 rows / 167 KB), not
  just that the site loads. Ran a full secret scan across git history before
  making the repo public — clean, no Databricks token or TfNSW key ever committed.
- 🟨 Expand DQ suite: ✅ `dbt source freshness` added on `gtfs_rt_trip_updates` and
  `gtfs_service_alerts` (warn >30min stale, error >90min — sized around the 15-min
  poll interval), run as a non-blocking diagnostic step in the scheduled pipeline
  itself, not just available on demand. The Pipeline Health Tableau tab (visualizing
  this + the orphan/outlier rates already tracked in Silver) still needs your hands
  in Tableau, same as the other pending dashboard work.
- ✅ Small ML delay-risk model ([ml/train_delay_risk_model.py](../ml/train_delay_risk_model.py)):
  Logistic Regression vs. Random Forest, temporal train/test split (day 1 → day
  2), class-imbalance-aware evaluation, scored into `gold.mart_trip_delay_risk_score`.
  **Real result, reported honestly**: ROC-AUC ~0.66, weak precision/recall (~0.13)
  on the "late" class — expected given only 2 days of data and a small feature
  set, and stated plainly in [ml/README.md](../ml/README.md) rather than dressed
  up. MLflow logging attempted and confirmed unavailable (`403: ... required
  scopes: mlflow` — same SQL-only-token pattern as everywhere else in this
  project), not silently skipped.
- ⬜ Architecture diagram + runbook in `docs/`
- ⬜ *(stretch, optional)* Structured Streaming/Auto Loader for RT ingestion

---

## Explicitly out of scope (see PROJECT_PLAN §17 for why)

Airflow/Dagster, Kafka/streaming infra, a custom web frontend, multi-cloud, deep
learning or model serving, full historical depth across all 4 modes in the MVP,
hand-rolled GTFS parsers, a custom orchestrator.
