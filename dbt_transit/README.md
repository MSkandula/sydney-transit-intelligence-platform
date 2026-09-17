# dbt_transit/

dbt Core project (dbt-databricks adapter) for Silver + Gold. **Live and running** —
this is what the scheduled pipeline (`scripts/run_pipeline.sh`) actually runs now,
not just a Phase 3 aspiration.

## Layout

```
models/
  staging/       one model per Bronze source, light typing/renaming, dbt sources.yml
  intermediate/  int_trip_stop_performance — dedup + schedule reconciliation
                 (the "Silver" logic, ported from ingestion/build_silver.py)
  marts/         dim_date, dim_route, dim_stop, fact_trip_stop_performance,
                 fact_service_alerts, mart_route_daily_performance,
                 mart_line_delay_concentration, mart_alert_delay_impact
macros/
  generate_schema_name.sql   makes a model's +schema config the literal schema name
                             (staging/silver/gold), not "<target>_gold" — the dbt
                             default concatenation behavior would've split this
                             project's tables across schemas dbt didn't intend
tests/           (custom singular tests go here if/when one doesn't fit a
                 generic schema test — none needed yet)
```

`fact_trip_stop_performance` is the one incremental model, merged on
`(service_date, trip_id, stop_id, stop_sequence)` — see the model file's header
comment and [docs/data_model.md](../docs/data_model.md) for why `stop_id` is part
of that key (a real TfNSW data quality issue, caught by a dbt test on real
accumulated data, not assumed in advance).

## Running it

```bash
cd dbt_transit
set -a; source ../.env; set +a   # DATABRICKS_HOST/TOKEN/HTTP_PATH into the shell env
dbt deps      # fetches dbt_utils (used for unique_combination_of_columns, accepted_range)
dbt build     # runs models + tests together
dbt docs generate && dbt docs serve   # browse the docs site locally
```

Needs `~/.dbt/profiles.yml` — copy [profiles.yml.example](profiles.yml.example) there
and fill in your username; see [PREREQUISITES.md](../PREREQUISITES.md).

## Real things this project's first build caught

Kept here rather than only in commit messages, since these are exactly the kind of
findings worth being able to point to directly:

1. **`REPLACEMENT` schedule_relationship** — an `accepted_values` test failed on the
   very first `dbt build`. TfNSW's feed uses this GTFS-RT enum value for bus-replaces-
   train services, which my initial accepted-values list (written from general GTFS-RT
   spec knowledge) didn't include. Fixed by adding it, once confirmed against real
   feed data rather than guessed.
2. **`stop_sequence` isn't always unique per trip** — a `unique_combination_of_columns`
   test on `fact_trip_stop_performance` failed with 1,348 violations the first time
   this project had two days of real data to test against. Root cause: TfNSW reports
   `stop_sequence=0` for every stop on at least some NSW TrainLink intercity trips.
   Fixed by adding `stop_id` to the fact table's grain — see the model file for the
   full investigation.
3. **Schema collision during cutover** — the Phase 1 hand-written
   `ingestion/build_gold.py` had already created a `workspace.gold.fact_trip_stop_performance`
   table with a different (incompatible) column set. dbt's incremental model tried to
   `MERGE` into it and failed with `DELTA_MERGE_UNRESOLVED_EXPRESSION`. Fixed by
   dropping the legacy table so dbt could create its own fresh — the intended
   outcome of the cutover, not a workaround.

## Relationship to the Phase 1 hand-written SQL

`ingestion/build_silver.py` and `ingestion/build_gold.py` are kept in the repo as
the Phase 1 MVP approach — they proved the pipeline and model shape before this dbt
project existed, and they're a legitimate answer to "what did you build before you
had dbt tests." They are **not run by the scheduled pipeline anymore** — running
both against the same `silver`/`gold` schemas would corrupt each other's table
structures (this happened once during the cutover, see above). `scripts/run_pipeline.sh`
now runs `dbt build` instead.
