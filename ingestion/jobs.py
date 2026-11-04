"""Container entry points for the two scheduled Azure jobs.

    python ingestion/jobs.py ingest      every 15 min: poll TfNSW, archive to Azure storage
    python ingestion/jobs.py transform   hourly: sync to Databricks, Bronze, dbt, health, extracts

Same code, same steps as scripts/run_pipeline.sh (which stays for local use), split in two:
ingestion only needs storage, so Databricks is touched once an hour instead of every
15 minutes. The Free Edition workspace has a fair-use compute quota, and the old
every-15-minutes schedule is what got it shut down on 3 Nov 2026.

Exit code 0 means every step passed. The last log line is `done OK` or `done FAILED: <steps>`
(the same convention the laptop pipeline uses), and a non-zero exit marks the job execution
as failed in Azure, which is what the failure alert watches.
"""

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import azure_storage
from config import AGENCY, LOCAL_LANDING_DIR, REPO_ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("jobs")

DBT_DIR = REPO_ROOT / "dbt_transit"
STATIC_MAX_AGE_HOURS = 24
SYNC_DAYS = int(os.environ.get("SYNC_DAYS", "7"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def static_refresh_due(
    max_age_hours: int = STATIC_MAX_AGE_HOURS, now: datetime | None = None
) -> bool:
    """True when the timetable has not been downloaded for a day. Ask the archive when Azure
    is configured (a container has no disk history), otherwise the local files."""
    now = now or _now()
    if azure_storage.is_configured():
        last = azure_storage.latest_modified(f"gtfs_static/{AGENCY}/")
    else:
        zips = list((LOCAL_LANDING_DIR / "gtfs_static" / AGENCY).glob("*.zip"))
        times = [datetime.fromtimestamp(z.stat().st_mtime, timezone.utc) for z in zips]
        last = max(times, default=None)
    return last is None or now - last > timedelta(hours=max_age_hours)


def _dbt(*args: str) -> int:
    profiles = os.environ.get("DBT_PROFILES_DIR", str(Path.home() / ".dbt"))
    command = ["dbt", *args, "--project-dir", str(DBT_DIR), "--profiles-dir", profiles]
    return subprocess.run(command, check=False).returncode


class Runner:
    """Runs steps in order, remembers which failed, and prints the final status line."""

    def __init__(self, name: str):
        self.name = name
        self.failed: list[str] = []

    def step(self, step_name: str, fn: Callable[[], int | None], critical: bool = False) -> bool:
        log.info("--- step: %s", step_name)
        try:
            ok = (fn() or 0) == 0
        except Exception:
            log.exception("Step raised: %s", step_name)
            ok = False
        if not ok:
            self.failed.append(step_name)
            log.error("!!! step failed: %s", step_name)
        return ok or not critical

    def finish(self) -> int:
        stamp = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.failed:
            log.info("===== %s done OK %s =====", self.name, stamp)
            return 0
        log.error("===== %s done FAILED: %s %s =====", self.name, " ".join(self.failed), stamp)
        return 1


def ingest() -> int:
    if not azure_storage.is_configured():
        raise RuntimeError("The ingest job archives to Azure: set AZURE_STORAGE_ACCOUNT first.")
    os.environ.setdefault("UPLOAD_TO_DATABRICKS", "false")

    import gtfs_alerts_ingest
    import gtfs_rt_ingest

    runner = Runner("ingest")
    runner.step("rt_ingest", gtfs_rt_ingest.main)
    runner.step("alerts_ingest", gtfs_alerts_ingest.main)
    return runner.finish()


def transform() -> int:
    runner = Runner("transform")
    # The transform job is the one that talks to Databricks.
    os.environ["UPLOAD_TO_DATABRICKS"] = "true"

    if static_refresh_due():
        import gtfs_static_ingest

        runner.step("static_ingest", gtfs_static_ingest.main)

    import check_pipeline_health
    import export_gold_extracts
    import land_bronze
    import sync_to_volume

    # Databricks being unreachable fails the first critical step and stops the chain, so a
    # shut-down warehouse is not hammered with a dozen more doomed sessions.
    synced = runner.step(
        "sync_to_volume", lambda: sync_to_volume.sync("azure", SYNC_DAYS), critical=True
    )
    if not synced:
        return runner.finish()
    if not runner.step("land_bronze", land_bronze.main, critical=True):
        return runner.finish()

    build_ok = runner.step("dbt_build", lambda: _dbt("build"))
    runner.step("dbt_freshness", lambda: _dbt("source", "freshness"))
    runner.step("health_check", check_pipeline_health.main)
    if build_ok:
        runner.step("export_extracts", lambda: _export_extracts(export_gold_extracts))
    return runner.finish()


def _export_extracts(export_module) -> int:
    """Write the Tableau CSVs and, in Azure, keep them in the extracts container."""
    result = export_module.main()
    if result == 0 and azure_storage.is_configured():
        for csv_path in sorted(export_module.EXPORT_DIR.glob("*.csv")):
            azure_storage.upload_file(csv_path, csv_path.name, azure_storage.extracts_container())
    return result


COMMANDS = {"ingest": ingest, "transform": transform}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in COMMANDS:
        print(f"usage: jobs.py {'|'.join(COMMANDS)}", file=sys.stderr)
        return 2
    return COMMANDS[args[0]]()


if __name__ == "__main__":
    sys.exit(main())
