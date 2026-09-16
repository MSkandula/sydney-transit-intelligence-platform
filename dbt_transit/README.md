# dbt_transit/

dbt Core project (dbt-databricks adapter) for the Gold layer.

This is a **Phase 3** deliverable — Phase 1's Gold tables are hand-written SQL,
deliberately, to prove the pipeline before adding dbt's structure on top. See
[PROJECT_PLAN.md](../PROJECT_PLAN.md) §6/§8 for what belongs here and
[docs/data_model.md](../docs/data_model.md) for the schema this project will implement.

Planned layout once started:
```
models/
  staging/     one model per Bronze source, light typing/renaming only
  marts/       dim_*, fact_*, mart_* per docs/data_model.md
tests/         custom singular tests (e.g. no duplicate trip-stop per service date)
```
