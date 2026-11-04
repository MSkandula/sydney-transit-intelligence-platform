"""Where a freshly captured file goes next.

Every ingest script saves a file locally, then calls `land_file`. Depending on the
environment that means:

- Azure archive (when `AZURE_STORAGE_ACCOUNT` / a connection string is set): copy to the
  raw container, the durable record of every poll.
- Databricks volume (default when `DATABRICKS_HOST` is set, so the laptop pipeline behaves
  exactly as before; set `UPLOAD_TO_DATABRICKS=false` to skip it).

The Azure ingest job turns the Databricks upload off. A Free Edition workspace has a
fair-use compute quota; opening a SQL session every 15 minutes kept the warehouse awake
around the clock and (on 3 Nov 2026) got it shut down. Ingestion now only needs storage,
and the hourly transform job uploads everything that is new in one short session.
"""

import logging
import os
from pathlib import Path

import azure_storage

log = logging.getLogger(__name__)


def archive_enabled() -> bool:
    enabled = os.environ.get("ARCHIVE_TO_AZURE", "true").lower() != "false"
    return azure_storage.is_configured() and enabled


def databricks_upload_enabled() -> bool:
    flag = os.environ.get("UPLOAD_TO_DATABRICKS")
    if flag is not None:
        return flag.strip().lower() in ("1", "true", "yes")
    return bool(os.environ.get("DATABRICKS_HOST"))


def land_file(local_path: Path, subpath: str) -> None:
    """subpath is relative to the landing root, for example
    gtfs_rt_trip_updates/sydneytrains/dt=2026-11-05/20261105T000000Z.parquet. Raises on failure."""
    if archive_enabled():
        azure_storage.upload_file(local_path, subpath)

    if databricks_upload_enabled():
        from databricks_upload import upload_to_volume

        upload_to_volume(local_path, subpath)
    else:
        log.info("Databricks upload skipped for %s", subpath)
