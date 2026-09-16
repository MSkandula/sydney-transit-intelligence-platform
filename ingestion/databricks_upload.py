"""Upload a local file into a Databricks Unity Catalog Volume.

Uses the Databricks SQL connector's `PUT` staging command rather than the Files
REST API — the Free Edition personal access token this project uses doesn't carry
the `files` scope needed for the REST API (confirmed by testing, not assumed), but
SQL warehouse access works fine and `PUT`/`LIST`/`REMOVE` cover the same need.
"""

import logging
import os
from pathlib import Path

from databricks import sql
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.getLogger("databricks.sql").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

CATALOG = "workspace"
BRONZE_VOLUME = f"/Volumes/{CATALOG}/bronze/raw_landing"


def connect():
    host = os.environ["DATABRICKS_HOST"].replace("https://", "")
    return sql.connect(
        server_hostname=host,
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
        staging_allowed_local_path=str(Path.home()) if Path.home().exists() else "/tmp",
    )


def upload_to_volume(local_path: Path, volume_subpath: str) -> str:
    """volume_subpath is relative to BRONZE_VOLUME, e.g.
    'gtfs_static/sydneytrains/20260916T115808Z_17f09b0539f6.zip'."""
    remote_path = f"{BRONZE_VOLUME}/{volume_subpath}"
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(f"PUT '{local_path}' INTO '{remote_path}' OVERWRITE")
        cur.close()
    finally:
        conn.close()
    log.info("Uploaded %s -> %s", local_path, remote_path)
    return remote_path
