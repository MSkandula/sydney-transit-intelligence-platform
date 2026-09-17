# Architecture

This reflects what's actually built and running, not the original aspiration —
see [PROJECT_PLAN.md](../PROJECT_PLAN.md) for how a few pieces of this changed
along the way (and why), and [ROADMAP.md](../ROADMAP.md) for current status.

```mermaid
flowchart TD
    subgraph ext["TfNSW Open Data Hub"]
        static["GTFS Static Schedule<br/>(v1, ~weekly)"]
        rt["GTFS-Realtime Trip Updates<br/>(v2, polled every 15 min)"]
        alerts["GTFS-Realtime Service Alerts<br/>(v2, polled every 15 min)"]
    end

    subgraph sched["Local scheduling — macOS launchd, every 15 min"]
        pipeline["scripts/run_pipeline.sh"]
    end

    subgraph ingest["Python ingestion"]
        rt_ingest["gtfs_rt_ingest.py"]
        alerts_ingest["gtfs_alerts_ingest.py"]
        static_ingest["gtfs_static_ingest.py<br/>(run manually, not scheduled)"]
    end

    subgraph dbx["Databricks Free Edition — Unity Catalog, workspace catalog"]
        volume["bronze.raw_landing<br/>(Unity Catalog Volume)"]
        bronze["Bronze — 7 Delta tables<br/>read_files() + COPY INTO<br/>(land_bronze.py, SQL only)"]
        subgraph dbt["dbt Core (dbt-databricks)"]
            staging["staging — 8 views"]
            silver["silver.int_trip_stop_performance<br/>(dedup + schedule reconciliation)"]
            gold["gold — 8 marts<br/>incremental fact + 2 business-impact marts"]
        end
    end

    ml["ml/train_delay_risk_model.py<br/>(pandas + scikit-learn, standalone)"]
    csv["tableau/extracts/*.csv"]
    tableau["Tableau Public<br/>(2 published dashboards)"]

    subgraph ci["GitHub Actions"]
        ci_test["ci.yml — ruff + pytest<br/>on every push/PR"]
        ci_dbt["dbt-ci.yml — dbt build<br/>against an isolated ci schema"]
    end

    static --> static_ingest
    rt --> rt_ingest
    alerts --> alerts_ingest

    pipeline --> rt_ingest
    pipeline --> alerts_ingest

    static_ingest --> volume
    rt_ingest --> volume
    alerts_ingest --> volume
    volume --> bronze
    bronze --> staging --> silver --> gold

    gold --> ml
    gold --> csv --> tableau

    style ci fill:#f5f5f5,stroke:#999
```

## Why this shape, not the original plan

A few things changed from the initial design, all for confirmed reasons (verified
by testing, not assumed) rather than convenience — full detail in PROJECT_PLAN.md
and ROADMAP.md, summarized here:

- **Bronze and Silver/Gold both run as SQL/dbt, not PySpark notebooks.** This
  project's Databricks personal access token is scoped to `sql` only — Jobs,
  Workspace, Files, and Unity Catalog admin APIs all reject it. Confirmed by
  testing each directly.
- **Scheduling is a local `launchd` job, not Databricks Workflows.** Same
  token-scope reason — Workflows needs the Jobs API. `launchd` only runs while
  the Mac is awake, which is a real, stated limitation, not hidden.
- **`dbt build` replaced hand-written SQL for Silver/Gold once dbt_transit/ was
  built** (Phase 3) — both wrote to the same schemas, so only one could run
  against them at a time. The hand-written scripts stay in the repo as the
  Phase 1 reference.
- **The ML model and Bronze landing both run as plain Python/SQL, not PySpark**
  — same token-scope reason, and the data volume (tens of thousands of rows) is
  comfortably small enough locally for that to be the right call anyway.
