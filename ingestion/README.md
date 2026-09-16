# ingestion/

Python scripts that pull data from the TfNSW Open Data Hub and land it in Bronze.

Planned files (Phase 1):
- `gtfs_static_ingest.py` — download + version-tag a GTFS static feed snapshot
- `gtfs_rt_ingest.py` — poll GTFS-RT (trip updates first; vehicle positions and
  service alerts added in Phase 2), decode protobuf via `gtfs-realtime-bindings`
- `config.py` — API key handling (via environment variable / `.env`, never committed)

No pipeline code has been written yet — see [ROADMAP.md](../ROADMAP.md) Phase 1.
