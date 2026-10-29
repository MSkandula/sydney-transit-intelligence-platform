"""Fails (exit 1) when the pipeline is quietly not working.

Two silent failures went unnoticed for weeks on this project, both while the scheduled
run still printed "done": Bronze loading crashed on a column-type mismatch, and the static
timetable went stale so ~100% of live trips stopped matching it. This check turns both
into a visible failed run.
"""
import logging
import sys
from datetime import datetime, timezone

from databricks_upload import connect

MAX_HOURS_SINCE_LAST_INGEST = 3
MAX_ORPHAN_PCT_LATEST_DAY = 50.0
MIN_ROWS_FOR_ORPHAN_CHECK = 500

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("health")


def main() -> int:
    conn = connect()
    problems = []
    try:
        cur = conn.cursor()

        cur.execute("SELECT max(_ingested_at) FROM workspace.gold.fact_trip_stop_performance")
        last_ingest = cur.fetchone()[0]
        hours = (datetime.now(timezone.utc) - last_ingest).total_seconds() / 3600
        log.info("Newest row in Gold was ingested %.1f hours ago", hours)
        if hours > MAX_HOURS_SINCE_LAST_INGEST:
            problems.append(f"no new data reached Gold for {hours:.1f}h")

        cur.execute(
            """
            SELECT service_date, count(*) AS n,
                   100.0 * avg(CASE WHEN is_orphan_trip THEN 1 ELSE 0 END) AS orphan_pct
            FROM workspace.gold.fact_trip_stop_performance
            WHERE service_date = (SELECT max(service_date)
                                  FROM workspace.gold.fact_trip_stop_performance)
            GROUP BY service_date
            """
        )
        service_date, n, orphan_pct = cur.fetchone()
        log.info("Latest service_date %s: %d rows, %.1f%% orphan", service_date, n, orphan_pct)
        if n >= MIN_ROWS_FOR_ORPHAN_CHECK and orphan_pct > MAX_ORPHAN_PCT_LATEST_DAY:
            problems.append(
                f"{orphan_pct:.0f}% of trips on {service_date} don't match the static "
                "timetable (is gtfs_static_ingest.py running?)"
            )
    finally:
        conn.close()

    if problems:
        log.error("HEALTH CHECK FAILED: %s", "; ".join(problems))
        return 1
    log.info("Health check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
