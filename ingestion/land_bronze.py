"""Materialise Bronze Delta tables from what's already sitting in the
workspace.bronze.raw_landing Unity Catalog volume.

Runs entirely over the Databricks SQL warehouse connection (`databricks-sql-connector`)
rather than a PySpark notebook. That's a deliberate, verified choice, not a fallback:
the personal access token this project uses only carries the `sql` scope (confirmed by
testing — `jobs`, `workspace`, `files` and the Unity Catalog admin API all return
PermissionDenied on Free Edition), so the SQL warehouse is the one thing this token can
drive end-to-end. `read_files()` and `COPY INTO` cover everything Bronze needs to do:
- Static schedule: full CREATE OR REPLACE per run (matches the design — TfNSW
  republishes ~weekly and Bronze always reflects the single latest snapshot landed).
- Realtime trip updates + service alerts: COPY INTO, which tracks already-loaded
  files itself — this *is* the incremental loading mechanism described in
  PROJECT_PLAN.md §10, not a manual watermark reimplementation.

A separate PySpark notebook (notebooks/bronze/land_gtfs_bronze.py) covers the same
ground for when this is run inside the Databricks UI directly (full workspace-session
permissions, no token-scope limits) — that path is optional; this script is Phase 1's
actual, verified Bronze step.
"""

import logging
import os
import sys
import zipfile
from pathlib import Path

from databricks_upload import BRONZE_VOLUME, connect
from config import AGENCY, LOCAL_LANDING_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CATALOG = "workspace"

STATIC_FILES = {
    "routes.txt": "gtfs_static_routes",
    "stops.txt": "gtfs_static_stops",
    "trips.txt": "gtfs_static_trips",
    "stop_times.txt": "gtfs_static_stop_times",
    "calendar.txt": "gtfs_static_calendar",
}


def latest_static_zip() -> Path:
    static_dir = LOCAL_LANDING_DIR / "gtfs_static" / AGENCY
    zips = sorted(static_dir.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(
            f"No static zip in {static_dir} — run gtfs_static_ingest.py first."
        )
    return zips[-1]


def feed_version_from_filename(zip_path: Path) -> str:
    return zip_path.stem.split("_")[-1]


def upload_extracted_static_files(zip_path: Path, feed_version: str, cur) -> str:
    """Unzip locally (this token can't do it remotely — no compute/files access)
    and PUT each needed GTFS text file into a version-tagged volume path.
    Extracted under LOCAL_LANDING_DIR (not /tmp) — the SQL connector's PUT command
    only accepts local paths under its configured staging_allowed_local_path, which
    we set to the home directory in databricks_upload.connect()."""
    extract_dir = LOCAL_LANDING_DIR / "gtfs_static_extracted" / feed_version
    extract_dir.mkdir(parents=True, exist_ok=True)

    volume_dir = f"{BRONZE_VOLUME}/gtfs_static/{AGENCY}/extracted/{feed_version}"
    with zipfile.ZipFile(zip_path) as zf:
        for filename in STATIC_FILES:
            if filename not in zf.namelist():
                log.warning("%s not present in this feed — skipping", filename)
                continue
            zf.extract(filename, extract_dir)
            local_file = extract_dir / filename
            cur.execute(f"PUT '{local_file}' INTO '{volume_dir}/{filename}' OVERWRITE")
    return volume_dir


def land_static_bronze(cur) -> None:
    zip_path = latest_static_zip()
    feed_version = feed_version_from_filename(zip_path)
    volume_dir = upload_extracted_static_files(zip_path, feed_version, cur)

    for filename, table_name in STATIC_FILES.items():
        file_path = f"{volume_dir}/{filename}"
        cur.execute(
            f"""
            CREATE OR REPLACE TABLE {CATALOG}.bronze.{table_name} AS
            SELECT
                *,
                '{feed_version}' AS _feed_version,
                '{zip_path.name}' AS _source_file,
                current_timestamp() AS _ingested_at
            FROM read_files('{file_path}', format => 'csv', header => true)
            """
        )
        cur.execute(f"SELECT count(*) FROM {CATALOG}.bronze.{table_name}")
        row_count = cur.fetchone()[0]
        log.info("%s: %d rows (feed_version=%s)", table_name, row_count, feed_version)


def land_parquet_bronze(cur, table_name: str, volume_subdir: str, ddl_columns: str) -> None:
    """Append-only Bronze landing for any parquet snapshot feed via COPY INTO.
    Shared by trip updates and service alerts — same feed shape (protobuf FeedMessage
    decoded to one Parquet snapshot per poll), same incremental-loading mechanism."""
    target = f"{CATALOG}.bronze.{table_name}"
    source_glob = f"{BRONZE_VOLUME}/{volume_subdir}/{AGENCY}/"

    cur.execute(f"CREATE TABLE IF NOT EXISTS {target} ({ddl_columns}) USING DELTA")
    cur.execute(f"COPY INTO {target} FROM '{source_glob}' FILEFORMAT = PARQUET")
    log.info("%s COPY INTO result: %s", table_name, cur.fetchall())

    cur.execute(f"SELECT count(*) FROM {target}")
    log.info("%s now has %d total rows", target, cur.fetchone()[0])


def land_realtime_bronze(cur) -> None:
    land_parquet_bronze(
        cur,
        "gtfs_rt_trip_updates",
        "gtfs_rt_trip_updates",
        """
        entity_id STRING,
        trip_id STRING,
        route_id STRING,
        start_date STRING,
        schedule_relationship STRING,
        stop_id STRING,
        stop_sequence BIGINT,
        arrival_delay_seconds DOUBLE,
        arrival_time DOUBLE,
        departure_delay_seconds DOUBLE,
        departure_time DOUBLE,
        stop_schedule_relationship STRING,
        feed_timestamp TIMESTAMP,
        _ingested_at TIMESTAMP,
        dt DATE
        """,
    )


def land_alerts_bronze(cur) -> None:
    land_parquet_bronze(
        cur,
        "gtfs_service_alerts",
        "gtfs_service_alerts",
        """
        entity_id STRING,
        cause STRING,
        effect STRING,
        header_text STRING,
        description_text STRING,
        route_id STRING,
        stop_id STRING,
        trip_id STRING,
        active_period_start TIMESTAMP,
        active_period_end TIMESTAMP,
        _ingested_at TIMESTAMP,
        dt DATE
        """,
    )


def main() -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(f"USE CATALOG {CATALOG}")
        land_static_bronze(cur)
        land_realtime_bronze(cur)
        land_alerts_bronze(cur)
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
