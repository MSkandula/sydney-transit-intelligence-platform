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

- `databricks_upload.py` — uploads a local file into the
  `workspace.bronze.raw_landing` Unity Catalog volume via the SQL connector's `PUT`
  command (not the Files REST API — this project's PAT doesn't carry the `files`
  scope; SQL access is unrestricted, so that's the path used throughout).
- `land_bronze.py` — materialises Bronze Delta tables from whatever's landed in the
  volume: `CREATE OR REPLACE TABLE ... read_files(...)` per static GTFS file, `COPY
  INTO` for realtime trip updates (which tracks already-loaded files itself).

Run from the repo root with the venv active:
```bash
python ingestion/gtfs_static_ingest.py   # lands locally + uploads to the volume
python ingestion/gtfs_rt_ingest.py       # same
python ingestion/land_bronze.py          # volume -> Bronze Delta tables
```
Needs `TFNSW_API_KEY` and the `DATABRICKS_*` variables set in `.env` (copy
`.env.example`) — see [PREREQUISITES.md](../PREREQUISITES.md).

Unit tests for the decode/flatten logic (no network needed) are in
[tests/test_gtfs_rt_ingest.py](../tests/test_gtfs_rt_ingest.py) — run `pytest` from
the repo root.
