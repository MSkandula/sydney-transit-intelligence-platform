# .github/workflows/

CI/CD pipelines — a **Phase 5** deliverable (see ROADMAP.md).

Planned:
- `ci.yml` — lint (ruff/black) + pytest on every push
- `dbt-ci.yml` — `dbt build`/`dbt test` against a dedicated CI schema on Databricks SQL
  warehouse, on PRs touching `dbt_transit/`
- dbt docs published to GitHub Pages on merge to `main`
