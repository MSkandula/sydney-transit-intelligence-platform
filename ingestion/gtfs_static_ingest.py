"""Pull one GTFS static schedule snapshot for Sydney Trains and land it locally.

Phase 1: lands to data/bronze/gtfs_static/ (local, git-ignored). Phase 2 replaces the
local landing step with a direct write into a Databricks Unity Catalog Volume — the
fetch/versioning logic here doesn't change.
"""

import hashlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import AGENCY, GTFS_SCHEDULE_BASE_URL, LOCAL_LANDING_DIR, auth_headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


def fetch_static_schedule(agency: str = AGENCY) -> bytes:
    url = f"{GTFS_SCHEDULE_BASE_URL}/{agency}"
    response = requests.get(url, headers=auth_headers(), timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    content = response.content
    if not content:
        raise ValueError(f"Empty response body from {url}")
    return content


def feed_version_tag(content: bytes) -> str:
    """Short content hash — lets Silver detect 'is this actually a new schedule?'
    without trusting a timestamp alone (TfNSW republishes even with no real change)."""
    return hashlib.sha256(content).hexdigest()[:12]


def save_snapshot(content: bytes, agency: str = AGENCY) -> Path:
    version = feed_version_tag(content)
    captured_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = LOCAL_LANDING_DIR / "gtfs_static" / agency
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{captured_at}_{version}.zip"
    out_path.write_bytes(content)
    return out_path


def main() -> int:
    try:
        content = fetch_static_schedule()
    except requests.RequestException:
        log.exception("Failed to fetch GTFS static schedule for %s", AGENCY)
        return 1

    out_path = save_snapshot(content)
    log.info(
        "Saved static schedule snapshot: %s (%d bytes)", out_path, len(content)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
