"""Upload landed files that are missing from the Databricks volume. Idempotent.

Why this exists: an upload can fail (Databricks refused new sessions for two days in
Nov 2026) and the file then exists only on local disk or in the Azure archive. COPY INTO can
only load what is in the volume, so this step closes the gap, and it makes ingestion
independent of Databricks being up at the moment a poll happens.

Sources: the local landing directory, or the Azure raw container. One SQL session is used
for the whole batch, which keeps Free Edition warehouse usage low.

    python ingestion/sync_to_volume.py --source local --days 7
    python ingestion/sync_to_volume.py --source azure --days 7 --dry-run
"""

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import azure_storage
from config import AGENCY, LOCAL_LANDING_DIR
from databricks_upload import BRONZE_VOLUME, connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FEEDS = ["gtfs_rt_trip_updates", "gtfs_service_alerts"]
DT_PATTERN = re.compile(r"dt=(\d{4}-\d{2}-\d{2})/")


@dataclass(frozen=True)
class Candidate:
    # Path relative to the volume root: <feed>/<agency>/dt=YYYY-MM-DD/<file>.parquet
    subpath: str
    local_path: Path | None = None
    blob_name: str | None = None

    @property
    def directory(self) -> str:
        return self.subpath.rsplit("/", 1)[0]

    @property
    def name(self) -> str:
        return self.subpath.rsplit("/", 1)[1]


def _recent(subpath: str, cutoff: date) -> bool:
    match = DT_PATTERN.search(subpath)
    return bool(match) and date.fromisoformat(match.group(1)) >= cutoff


def local_candidates(cutoff: date, root: Path | None = None) -> list[Candidate]:
    root = root or LOCAL_LANDING_DIR
    found = []
    for feed in FEEDS:
        base = root / feed / AGENCY
        for path in sorted(base.glob("dt=*/*.parquet")):
            subpath = f"{feed}/{AGENCY}/{path.parent.name}/{path.name}"
            if _recent(subpath, cutoff):
                found.append(Candidate(subpath=subpath, local_path=path))
    return found


def azure_candidates(cutoff: date) -> list[Candidate]:
    found = []
    for feed in FEEDS:
        for blob in azure_storage.list_blobs(f"{feed}/{AGENCY}/"):
            if blob.name.endswith(".parquet") and _recent(blob.name, cutoff):
                found.append(Candidate(subpath=blob.name, blob_name=blob.name))
    return sorted(found, key=lambda c: c.subpath)


def volume_listing(cur, directory: str) -> set[str]:
    """File names already in one volume directory (empty if the directory does not exist yet)."""
    try:
        cur.execute(f"LIST '{BRONZE_VOLUME}/{directory}/'")
        columns = [d[0] for d in cur.description]
        name_index = columns.index("name") if "name" in columns else 1
        return {row[name_index] for row in cur.fetchall()}
    except Exception:
        log.info("Volume directory %s not listable yet; treating as empty", directory)
        return set()


def find_missing(cur, candidates: list[Candidate]) -> list[Candidate]:
    listings: dict[str, set[str]] = {}
    missing = []
    for candidate in candidates:
        if candidate.directory not in listings:
            listings[candidate.directory] = volume_listing(cur, candidate.directory)
        if candidate.name not in listings[candidate.directory]:
            missing.append(candidate)
    return missing


def upload_candidate(cur, candidate: Candidate) -> None:
    local_path = candidate.local_path
    downloaded = False
    if local_path is None:
        local_path = LOCAL_LANDING_DIR / "_sync_tmp" / candidate.subpath
        azure_storage.download_file(candidate.blob_name, local_path)
        downloaded = True
    try:
        remote = f"{BRONZE_VOLUME}/{candidate.subpath}"
        cur.execute(f"PUT '{local_path}' INTO '{remote}' OVERWRITE")
    finally:
        if downloaded:
            local_path.unlink(missing_ok=True)


def sync(source: str, days: int, dry_run: bool = False, today: date | None = None) -> int:
    """Returns the number of files that failed to upload (0 means fully in sync)."""
    cutoff = (today or date.today()) - timedelta(days=days)
    candidates = local_candidates(cutoff) if source == "local" else azure_candidates(cutoff)
    log.info("%d %s files in the last %d days", len(candidates), source, days)
    if not candidates:
        return 0

    conn = connect()
    failed = 0
    try:
        cur = conn.cursor()
        missing = find_missing(cur, candidates)
        log.info("%d of them are missing from the Databricks volume", len(missing))
        if dry_run:
            for candidate in missing[:20]:
                log.info("would upload %s", candidate.subpath)
            return 0
        for candidate in missing:
            try:
                upload_candidate(cur, candidate)
            except Exception:
                failed += 1
                log.exception("Upload failed for %s", candidate.subpath)
        cur.close()
    finally:
        conn.close()
    log.info("Sync finished: %d uploaded, %d failed", len(missing) - failed, failed)
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source", choices=["local", "azure"], default="local")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return 1 if sync(args.source, args.days, args.dry_run) else 0


if __name__ == "__main__":
    sys.exit(main())
