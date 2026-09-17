# ingestion/

Python scripts that pull data from the TfNSW Open Data Hub and land it in Bronze.

- `config.py` — loads `TFNSW_API_KEY` from `.env`; endpoint constants (v1 schedule,
  v2 realtime); `AGENCY = "sydneytrains"` for the Phase 1 MVP scope.
- `gtfs_static_ingest.py` — `GET /v1/gtfs/schedule/sydneytrains`, content-hashes the
  zip for version tagging, lands it under `data/bronze/gtfs_static/` (local for now;
  Phase 2 swaps this for a direct write to a Databricks Volume).
- `gtfs_rt_ingest.py` — `GET /v2/gtfs/realtime/sydneytrains` (Sydney Trains requires
  v2, not v1), decodes the protobuf `FeedMessage`, flattens to one row per
  trip-stop update, lands as Parquet under `data/bronze/gtfs_rt_trip_updates/`.
- `gtfs_alerts_ingest.py` — `GET /v2/gtfs/alerts/sydneytrains`, decodes the alert
  `FeedMessage`, flattens to one row per (alert, informed entity), lands as Parquet
  under `data/bronze/gtfs_service_alerts/`. Explicitly casts nullable string columns
  before writing — an always-null column (e.g. `trip_id`, since this feed has no
  trip-level alerts so far) otherwise gets written with a schema that conflicts with
  Delta the moment a differently-typed file lands (hit this for real, fixed it).

- `databricks_upload.py` — uploads a local file into the
  `workspace.bronze.raw_landing` Unity Catalog volume via the SQL connector's `PUT`
  command (not the Files REST API — this project's PAT doesn't carry the `files`
  scope; SQL access is unrestricted, so that's the path used throughout).
- `land_bronze.py` — materialises Bronze Delta tables from whatever's landed in the
  volume: `CREATE OR REPLACE TABLE ... read_files(...)` per static GTFS file, `COPY
  INTO` for realtime trip updates and service alerts (which tracks already-loaded
  files itself).
- `build_silver.py`, `build_gold.py`, `export_gold_extracts.py` — the rest of the
  pipeline; see [docs/data_model.md](../docs/data_model.md) for what each Gold table
  and mart actually contains.

Run from the repo root with the venv active — or just run
[scripts/run_pipeline.sh](../scripts/run_pipeline.sh), which runs the full sequence
in the right order (that's also what the scheduled job runs, see
[docs/scheduled_ingestion.md](../docs/scheduled_ingestion.md)):
```bash
python ingestion/gtfs_static_ingest.py   # lands locally + uploads to the volume
python ingestion/gtfs_rt_ingest.py       # same
python ingestion/gtfs_alerts_ingest.py   # same
python ingestion/land_bronze.py          # volume -> Bronze Delta tables
python ingestion/build_silver.py
python ingestion/build_gold.py
python ingestion/export_gold_extracts.py
```
Needs `TFNSW_API_KEY` and the `DATABRICKS_*` variables set in `.env` (copy
`.env.example`) — see [PREREQUISITES.md](../PREREQUISITES.md).

Unit tests for the decode/flatten logic (no network needed) are in
[tests/test_gtfs_rt_ingest.py](../tests/test_gtfs_rt_ingest.py) and
[tests/test_gtfs_alerts_ingest.py](../tests/test_gtfs_alerts_ingest.py) — run
`pytest` from the repo root.
