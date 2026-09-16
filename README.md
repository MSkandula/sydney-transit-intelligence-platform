# Sydney Transit Intelligence Platform

An end-to-end analytics platform that ingests real-time and scheduled public transport
data from Transport for NSW (TfNSW) to measure, explain, and surface where Sydney's
public transport network is underperforming — and why.

This is a portfolio project built to demonstrate data engineering and analytics
engineering skills that complement (not repeat) my existing PostgreSQL/pandas/Tableau/
Power BI projects: API ingestion, Databricks + PySpark, Delta Lake, a Bronze/Silver/Gold
lakehouse, dbt, incremental pipelines, data quality testing, Git-based CI/CD, and basic
orchestration — all built on entirely free tooling.

Full plan: see [PROJECT_PLAN.md](PROJECT_PLAN.md) for the business case, architecture,
data model, and design decisions, and [ROADMAP.md](ROADMAP.md) for the phased build
plan and current status.

## Why this project exists

My existing projects (PAYscope, E-Commerce Delivery & Retention Analysis) prove SQL,
Python, Power BI/DAX, Tableau, and data-quality thinking on static, already-collected
datasets. They don't demonstrate ingesting live external data, working with a lakehouse,
or building tested, orchestrated pipelines — which is what separates a Data Analyst
portfolio from one that also stands up for Junior Data Engineer / Analytics Engineer
roles in the Sydney market. This project closes that gap using a real, public,
Sydney-relevant data source (TfNSW GTFS feeds) instead of a generic Kaggle CSV.

## Tech stack

| Layer | Tool | Why |
|---|---|---|
| Ingestion | Python (`requests`, `gtfs-realtime-bindings`) | Pull GTFS static + realtime (protobuf) feeds from TfNSW's Open Data Hub |
| Storage / compute | Databricks Free Edition + PySpark + Delta Lake | Free lakehouse compute; ACID tables; handles schema drift across weekly static releases |
| Transformation | dbt Core (dbt-databricks adapter) | Silver → Gold business logic, testing, documentation, version control for SQL |
| Orchestration | Databricks Workflows | Free, in-platform job scheduling — no Airflow needed for this scale |
| CI/CD | GitHub Actions | Lint + unit test ingestion code, run `dbt build` against a CI schema on every PR |
| BI | Tableau Public | Operational dashboards published from Gold-layer extracts |
| ML (secondary) | scikit-learn / XGBoost | Small delay-risk classifier scored from Gold data — not the focus |

## Repository map

```
ingestion/       Python scripts that pull GTFS static + GTFS-RT feeds from TfNSW
notebooks/       Databricks notebooks: bronze landing, silver transforms, ML scoring
dbt_transit/     dbt project: Gold-layer star schema, tests, documentation
tableau/         Tableau Public workbooks + exported extracts
tests/           pytest unit tests for ingestion/parsing logic
docs/            Data model reference, architecture notes
.github/workflows/  CI/CD pipelines
PROJECT_PLAN.md  Full design doc — business case through interview prep
ROADMAP.md       Phased build plan and status tracker
```

## Status

Planning complete. Build not started. See [ROADMAP.md](ROADMAP.md) for Phase 1 (MVP) scope.
