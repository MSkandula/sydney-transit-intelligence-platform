# tests/

pytest unit tests for ingestion and parsing logic — not dbt tests (those live in
`dbt_transit/tests/`).

Planned (Phase 1): tests for the protobuf decode step in
`ingestion/gtfs_rt_ingest.py` — malformed/empty feed handling, required-field checks.
Wired into CI in Phase 5 (see [.github/workflows/](../.github/workflows/README.md)).
