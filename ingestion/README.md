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

Run from the repo root with the venv active:
```bash
python ingestion/gtfs_static_ingest.py
python ingestion/gtfs_rt_ingest.py
```
Both need `TFNSW_API_KEY` set in `.env` (copy `.env.example`) — see
[PREREQUISITES.md](../PREREQUISITES.md).

Unit tests for the decode/flatten logic (no network needed) are in
[tests/test_gtfs_rt_ingest.py](../tests/test_gtfs_rt_ingest.py) — run `pytest` from
the repo root.
