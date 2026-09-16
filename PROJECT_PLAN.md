# Project Plan — Sydney Transit Intelligence Platform

Status: **planning complete, build not started**. This doc is the source of truth for
scope and design decisions. Update it when a decision changes — don't let it go stale.

---

## 1. Business problem & objective

Transport for NSW publishes live GTFS-Realtime feeds (trip updates, vehicle positions,
service alerts) alongside the scheduled GTFS static timetable, but does not publish a
consolidated, historical, analysis-ready reliability dataset. The realtime feed is a
live snapshot — it only becomes useful for trend analysis once someone captures it over
time and reconciles it against the schedule. That reconciliation (which trip-stop was
late, by how much, and why) is the actual data engineering problem this project solves.

**Objective:** build a platform that ingests TfNSW's GTFS static + realtime feeds over
time, reconciles actual vs. scheduled performance, and surfaces which routes, stops,
and time windows are underperforming and what's associated with it (service alerts,
time of day, mode), through tested, documented, incrementally-loaded pipelines and
operational dashboards.

## 2. Hypothetical stakeholders

- **Network performance / service planning team** — primary user; wants to know where
  to focus reliability investment.
- **Operations control** — wants near-real-time visibility into current disruptions.
- **Customer experience / comms** — wants to know which alerts actually correlate with
  measurable service impact, to calibrate future rider communication.
- **Data & analytics leadership** — wants self-serve dashboards instead of one-off report
  requests.

## 3. Key business questions

1. Which routes and stops have the worst on-time running, and is it consistent or
   sporadic?
2. How does delay vary by time of day, day of week, and mode (train/bus/ferry/light rail)?
3. Do service alerts actually correlate with measurable delay spikes, or is impact
   overstated/understated?
4. Is unreliability concentrated in specific corridors/operators, or spread evenly?
5. Is reliability trending better or worse over the capture window?
6. (stretch, if patronage data is available) Does low reliability correlate with
   ridership drop-off on a route?

## 4. Data sources

All from the [TfNSW Open Data Hub](https://opendata.transport.nsw.gov.au/) (free,
requires a registered API key).

| Source | Contributes | Update cadence |
|---|---|---|
| GTFS Static Schedule | Routes, trips, stops, calendar — the dimensional backbone; also the "scheduled" side of every delay calculation | Weekly / on timetable change |
| GTFS-Realtime Trip Updates | Predicted vs. scheduled arrival/departure per trip-stop — the core delay fact | Polled every 1–5 min |
| GTFS-Realtime Vehicle Positions | Vehicle location/speed — supports dwell-time and running-time derived metrics | Polled every 1–5 min |
| GTFS-Realtime Service Alerts | Planned/unplanned disruptions, cause/effect codes | Polled every 1–5 min |
| Opal patronage data (optional, Gold-layer context only) | Demand context to pair with reliability findings | Periodic/aggregate |

Deliberately **not** using weather, external traffic, or social media data — out of
scope; adds ingestion complexity without a proportional business-question payoff.

## 5. End-to-end architecture (confirmed against current platform docs, Sept 2026)

```
TfNSW Open Data Hub
  - GTFS Static Schedule (daily-published zip)
  - GTFS-Realtime Trip Updates — Sydney Trains/Metro/Inner West Light Rail use the
    v2 dataset (v1 is superseded for these modes); bus/ferry/regional still use v1
  - upstream feed refreshes every ~15s; we poll every 5 min (see §11 — polling faster
    buys no real analytical value here and risks the Free Edition fair-usage cap)
        │
        ▼
Python ingestion (requests + gtfs-realtime-bindings)
  scheduled as a Databricks Job — plain scheduled batch, not continuous (see §11)
        │
        ▼
BRONZE  — Delta tables in Unity Catalog (preconfigured in Free Edition — no external
        │  cloud storage account needed; landed in a managed Volume, loaded as Delta)
        ▼  (PySpark, serverless compute)
SILVER  — Delta tables, cleaned/conformed/deduplicated, delay calculated
        │  (dbt Core + dbt-databricks, against Free Edition's one pre-provisioned
        │   "Serverless Starter Warehouse" — dev and CI both use this same warehouse,
        │   isolated by target schema, since Free Edition can't create new warehouses)
        ▼
GOLD    — Delta tables, star schema marts, dbt-tested and documented
        │
        ├──▶ Tableau Public — manual extract export + republish (Tableau Public has
        │     no scheduled-refresh mechanism for file-based sources; this is a real
        │     platform limit, not a shortcut, and worth naming directly in interviews)
        └──▶ small scikit-learn/XGBoost delay-risk model, scored back into Gold

GitHub + GitHub Actions: version control for all code (ingestion, notebooks, dbt
project); CI runs pytest + `dbt build` against a dedicated `ci` schema on the same
Free Edition warehouse, on every PR.
```

**Key infrastructure decision:** everything free. Ingestion, compute, and orchestration
run inside **Databricks Free Edition** (free workspace, serverless compute, Unity
Catalog storage, native Jobs for scheduling) — this avoids needing any paid cloud
storage while still giving a real lakehouse to build on. GitHub Actions is used for
CI/CD, not as the production scheduler.

**Confirmed platform facts this design assumes (verified via current docs, not memory):**
- Free Edition is serverless-only (no custom clusters); Unity Catalog is preconfigured;
  **max 5 concurrent job tasks per account**; exceeding the fair-usage quota shuts the
  workspace down for the rest of the day (or month, in extreme cases). → keep the job
  DAG small and sequential, poll conservatively.
- "Continuous" scheduling only works via bounded Structured Streaming triggers (e.g.
  `Trigger.AvailableNow`) — true always-on streaming isn't available on Free Edition. →
  don't build toward Structured Streaming for the MVP; a plain scheduled batch Job is
  both simpler to build/explain and the platform-idiomatic choice here.
- dbt connects to the one pre-provisioned Serverless Starter Warehouse; Free Edition
  can't create additional SQL warehouses.
- Tableau Public genuinely has no scheduled-refresh mechanism for file-based sources —
  confirmed, not a workaround-able limitation.

Sources: [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations) · [Sign up for Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition) · [TfNSW Realtime Trip Update v2](https://opendata.transport.nsw.gov.au/data/dataset/public-transport-realtime-trip-update-v2) · [dbt Databricks setup](https://docs.getdbt.com/docs/local/connect-data-platform/databricks-setup) · [Tableau data refresh](https://help.tableau.com/current/pro/desktop/en-us/refreshing_data.htm)

## 6. Bronze / Silver / Gold responsibilities

**Bronze** — raw landing, append-only, schema-on-read, minimal transformation.
- `bronze_gtfs_static_{routes,trips,stops,stop_times,calendar}` — one snapshot per
  static feed version
- `bronze_trip_updates`, `bronze_vehicle_positions`, `bronze_service_alerts` — one row
  per decoded protobuf entity per poll
- Every table carries ingestion metadata: `_ingested_at`, `_source_feed`, `_batch_id`.
- No deduplication, no joins, no business logic. If ingestion captured it, it's here.

**Silver** (PySpark) — cleaned, conformed, one clear grain per entity.
- Reconcile RT `trip_id`s against the correct static schedule **version** (TfNSW
  publishes new static feeds ~weekly; a trip_id is only meaningful against the static
  version active on that service date — a real, non-obvious GTFS gotcha worth knowing
  going in).
- Deduplicate repeated RT snapshots per trip-stop (a trip-stop is reported many times
  before it's actually reached — keep the latest snapshot before the event, using a
  window function over `_ingested_at`).
- Compute `scheduled_ts`, `actual_ts`, `delay_seconds`, `is_cancelled` per trip-stop.
- Quarantine (not silently drop) implausible records — see §9.

**Gold** (dbt) — business-facing star schema + pre-aggregated marts.
- `dim_date`, `dim_route`, `dim_stop`, `dim_trip` + `fact_trip_stop_performance`,
  `fact_service_alerts` (full definitions in [docs/data_model.md](docs/data_model.md)).
- `mart_route_daily_performance`, `mart_stop_daily_performance` — pre-aggregated,
  Tableau-ready.
- dbt tests + dbt docs live here.

## 7. Tool-to-layer mapping

| Tool | Used for |
|---|---|
| Python | Ingestion (API calls, protobuf decoding), unit tests, ML script |
| PySpark | Bronze → Silver (large joins, dedup via window functions, schema reconciliation) |
| SQL / dbt | Silver → Gold (business logic, star schema, tests, docs) |
| Delta Lake | Storage format at every layer (ACID, schema evolution, time travel for debugging) |
| Tableau Public | Gold-layer marts → dashboards (via exported extracts — Tableau Public has no live Databricks connector, see §12) |
| GitHub Actions | CI (lint, pytest, `dbt build`/`dbt test` on PR), dbt docs publish to GitHub Pages |

## 8. Star schema

Full grain, keys, and column-level detail in **[docs/data_model.md](docs/data_model.md)**.
Summary:

- `fact_trip_stop_performance` — grain: **one row per scheduled trip visiting one stop
  on one service date.** FKs to `dim_date`, `dim_route`, `dim_stop`, `dim_trip`.
  Measures: scheduled/actual arrival & departure timestamps, delay in seconds,
  cancelled/skipped flags.
- `fact_service_alerts` — grain: one row per alert × affected route/stop × active period.
- `mart_route_daily_performance` / `mart_stop_daily_performance` — grain: route/stop ×
  date, pre-aggregated (% on-time, avg delay, cancellations, trip count) for BI.
- Dimensions use surrogate keys generated in dbt; natural keys (`route_id`, `stop_id`,
  `trip_id`) retained as degenerate columns for traceability back to the raw feeds.

## 9. Data quality checks

- **Ingestion:** schema validation on protobuf decode; row-count sanity check vs. the
  previous run (catches a feed outage); log API response status + latency.
- **Bronze:** track raw record counts per batch; % of expected routes present per poll.
- **Silver:**
  - not-null on join keys after static/RT reconciliation
  - orphan check — RT records whose `trip_id` doesn't resolve to any static trip
    (flagged, not dropped — this is a genuine, common GTFS-RT/static mismatch)
  - exactly one final snapshot per trip-stop after dedup
  - range check on `delay_seconds` (implausible values quarantined, not deleted)
  - freshness check — no ingestion gap longer than the expected poll interval
- **Gold (dbt tests):** `unique` + `not_null` on all keys, `relationships` (fact FKs
  resolve in dims), `accepted_values` (mode in a known set), custom test for no
  duplicate trip-stop per service date.
- A small "pipeline health" view (% records passing DQ checks, ingestion freshness over
  time) is worth its own Tableau tab — it's a pipeline about reliability, so its own
  reliability is a legitimate, interview-worthy artifact.

## 10. Incremental ingestion & loading

- **GTFS static:** full-refresh per version, not per poll. Detect a new version via
  `feed_info.txt` version/hash; only reprocess Silver when a new version lands. Keep
  every version's snapshot in Bronze (partitioned by `feed_version`).
- **GTFS-RT (all three feeds):** append-only, one snapshot per poll tagged with
  `_ingested_at`. Silver processes incrementally using a **watermark** (only new
  `_ingested_at` partitions since the last successful run) — start with plain
  watermarked batch, not Structured Streaming/Auto Loader; that's a clearly-labelled
  Phase 5 stretch, not an MVP requirement.
- **dbt:** Gold fact models use `is_incremental()` with a `unique_key` of
  (`service_date`, `trip_id`, `stop_sequence`) so a re-run doesn't reprocess full
  history.

## 11. Orchestration (no paid services)

Three small Databricks Jobs (Free Edition, serverless compute only — confirmed limits
in §5 shape this design directly):

- **Job A — Ingest Realtime**: one task, scheduled every 5 min, calls the TfNSW GTFS-RT
  v2 trip updates endpoint, decodes protobuf, appends to Bronze. A single task per run
  stays well clear of the 5-concurrent-task account cap.
- **Job B — Ingest Static**: one task, scheduled weekly, refreshes the GTFS static
  snapshot and tags it with a feed version.
- **Job C — Daily Pipeline**: 2–3 **sequential** tasks in one job, scheduled once or
  twice daily: Silver PySpark transform → `dbt build` (Gold) → DQ check notebook.
  Keep this linear, not fan-out, to stay inside the concurrency cap.

This is a real, industry-used pattern (plenty of companies run Databricks Jobs instead
of Airflow at this scale) — a legitimate answer to "how did you orchestrate this," not
a toy.

- **GitHub Actions** is CI/CD, not production orchestration: runs on push/PR, and
  optionally a `workflow_dispatch`/cron step that triggers a Databricks Job via the
  Jobs REST API, to demonstrate the two systems talking to each other.
- **Deliberately not** attempting Structured Streaming/Auto Loader for the MVP — Free
  Edition's continuous scheduling only supports bounded triggers anyway, so a plain
  scheduled batch job is both simpler and platform-idiomatic here.
- **Deliberately not** standing up Airflow/Dagster/Prefect locally — unnecessary
  infrastructure for this scale when Databricks Jobs already covers it for free.

## 12. Tableau dashboards & KPIs

**Constraint to design around:** Tableau Public has no live connector to Databricks —
it only accepts extracts. Workflow: dbt Gold marts → a small scheduled export step
(SQL/Python) produces CSV/Hyper extracts → publish/refresh to Tableau Public manually
or on a documented cadence. This is a real, honest trade-off worth naming directly in
interviews ("why isn't this live?") rather than hiding.

Dashboards (matching the 3-page pattern from my existing Tableau work):

1. **Network Reliability Overview** — network-wide % on-time, avg delay trend, by-mode
   breakdown, day-of-week/time-of-day heatmap.
2. **Route & Stop Deep Dive** — worst-performing routes/stops (table + map), drill
   route → stop → trip, delay distribution.
3. **Service Alerts & Impact** — alerts timeline, cause/effect breakdown, delay
   before/during/after an alert's active period.
4. *(optional)* **Pipeline Health** — % records passing DQ tests, ingestion freshness —
   demonstrates engineering maturity alongside the BI work.

**KPIs:** % On-Time Running (reuse TfNSW's own published OTR definition/threshold per
mode for authenticity), average/median delay, cancellation rate, % trips missing RT
coverage, alert count by cause, worst 10 routes/stops.

## 13. ML component — small, secondary, clearly scoped

**Yes, but deliberately minor.** A single classification task: predict whether a given
trip-stop will be delayed beyond a threshold (e.g. >5 min), using Gold-layer features
(route, stop, time of day, day of week, rolling recent delay history, active-alert
flag). scikit-learn/XGBoost, one notebook, scored output written to a
`gold.trip_delay_risk_score` table and surfaced as a "predicted risk" indicator on the
Route Deep Dive dashboard. No model registry or serving endpoint required — logging
runs with MLflow (built into Databricks, free) is worth doing since it's a one-line
addition and a legitimate talking point, but the ML surface area stops there. It should
never become the headline of this project.

## 14. Recommended GitHub repository structure

Already scaffolded in this repo:

```
ingestion/          Python: gtfs_static_ingest.py, gtfs_rt_ingest.py, protobuf parsing
notebooks/          Databricks notebooks: bronze landing, silver transforms, ML scoring
dbt_transit/        dbt project — Gold star schema, tests, docs
tableau/            .twbx workbooks + exported extracts
tests/              pytest unit tests for ingestion/parsing logic
docs/               data_model.md, architecture notes
.github/workflows/  ci.yml, dbt-ci.yml
README.md           Elevator pitch + repo map
PROJECT_PLAN.md     This document
ROADMAP.md          Phased build plan + status
```

## 15. CI/CD & automated testing

- **pytest** on ingestion/parsing code (protobuf decode correctness, schema checks) —
  runs on every push via GitHub Actions.
- **`dbt build`/`dbt test`** in CI against a dedicated CI schema/catalog on the
  Databricks SQL warehouse (secrets-based token) — runs on PRs touching `dbt_transit/`.
- **Linting:** `ruff`/`black` for Python, `sqlfluff` for dbt SQL.
- **dbt docs** built and published to GitHub Pages on merge to `main`.
- Branch protection on `main`: PRs required, CI must pass (worth setting up even solo —
  it's the habit, not the audience, that the interview question is really about).

## 16. Phased roadmap

See **[ROADMAP.md](ROADMAP.md)** — kept as a separate, living checklist so it can be
updated per session without re-editing this design doc.

## 17. What NOT to build

- No Airflow/Dagster/Prefect — Databricks Workflows already covers orchestration.
- No Kafka/streaming infrastructure — scheduled polling of GTFS-RT is realistic and
  sufficient (it's literally how TfNSW expects the feed to be consumed).
- No custom web app/API frontend — Tableau Public is the delivery surface.
- No multi-cloud — Databricks Free Edition + GitHub only, nothing else.
- No over-scoped ML — no deep learning, no real-time model serving.
- No attempting all four modes at full historical depth in the MVP — expand gradually
  (see Roadmap Phase 1 scope: trains only).
- No hand-rolled GTFS parsers — use established libraries (`gtfs-realtime-bindings`,
  `gtfs_kit`/`partridge`) instead of reinventing protobuf/GTFS parsing.
- No custom orchestrator built in Python — resist the urge; use what's already free
  and built for this.

## 18. Skills this project supports per role (Sydney market)

- **Data Analyst:** SQL, KPI design, dashboard storytelling, stakeholder-question
  framing, reconciliation logic (static vs. realtime).
- **BI Analyst:** dimensional modeling, Tableau Public trade-offs, KPI governance, data
  dictionary discipline.
- **Junior Data Engineer:** API ingestion, protobuf parsing, incremental loading,
  Bronze/Silver/Gold design, Delta Lake, Databricks Workflows orchestration, CI/CD for
  data pipelines.
- **Analytics Engineer:** dbt modeling, testing, documentation, star schema design,
  git/PR-based development workflow, SQL transformation logic.

## 19. Likely interviewer questions this project generates

- Why polling GTFS-RT instead of a streaming/Kafka approach?
- How do you handle a new static schedule publishing while RT data still references
  the previous version's trip_ids?
- How did you validate that your delay calculations were actually correct?
- What happens to the pipeline if the TfNSW API goes down for a period?
- Why Bronze/Silver/Gold instead of one big table?
- Why dbt instead of writing SQL directly in notebooks?
- What was the hardest data quality issue you ran into, and how did you catch it?
- Why Tableau Public instead of a live-connected dashboard — what did that trade off?
- Where would the ML delay-risk model actually be used operationally?
- How would this scale to TfNSW's real production volumes?

## 20. Final simplified architecture & recommended MVP

**Simplified architecture for the first build pass:**

```
TfNSW GTFS static + trip updates (Sydney Trains only)
   → Python ingestion (local script or Databricks notebook)
   → Bronze Delta (Databricks Free Edition)
   → PySpark Silver (schedule reconciliation, dedup, delay calc)
   → hand-written SQL Gold (dbt deferred to Phase 3)
   → Tableau Public: one dashboard (On-Time Performance Overview)
   → GitHub repo, README, basic pytest (CI deferred to Phase 5)
```

**Recommended MVP scope (Phase 1):** Sydney Trains only, GTFS static + trip updates
only (skip vehicle positions and alerts for now), 1–2 weeks of captured data, one
Tableau dashboard. The goal of Phase 1 is proving the full path — ingest → reconcile →
one real, defensible insight — before adding breadth. See
[ROADMAP.md](ROADMAP.md) for the detailed Phase 1 checklist.
