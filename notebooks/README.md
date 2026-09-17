# notebooks/

Databricks notebooks (PySpark), exported as `.py` source for version control.

- `bronze/land_gtfs_bronze.py` — the PySpark equivalent of `ingestion/land_bronze.py`,
  for running inside the Databricks UI directly (a logged-in browser session has
  full workspace permissions regardless of this project's SQL-only-scoped token —
  see PROJECT_PLAN.md §5). Written but never executed; the SQL path is what
  actually runs. Optional, not required.

Silver and the ML delay-risk model ended up as standalone scripts instead of
notebooks under here — [dbt_transit/](../dbt_transit/) for Silver/Gold (SQL, not
PySpark) and [ml/](../ml/) for the model (plain Python over the SQL connector,
not PySpark) — for the same token-scope reason. Kept as top-level directories
rather than nested under `notebooks/` since neither one is actually a notebook.
