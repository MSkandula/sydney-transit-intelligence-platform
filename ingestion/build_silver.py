"""Build the Silver reconciliation table: one row per (trip, stop) actually observed
in the realtime feed, joined against the static schedule it belongs to.

Runs as SQL over the same Databricks SQL warehouse connection as land_bronze.py, for
the same confirmed reason (this token's scope covers `sql` only). Three things this
step does that Bronze deliberately doesn't:

1. Dedup — a trip-stop is reported in the RT feed many times before it's actually
   reached; keep only the latest snapshot per (trip_id, stop_id, stop_sequence).
2. Reconcile — join the RT trip_id against the static trips/stop_times it references.
   Empirically, 2,860/2,916 (98.1%) of RT rows in the first live pull matched directly
   on trip_id against the current static feed version — no ID-translation layer was
   needed for this snapshot. The ~2% that don't match are kept (left join), not
   dropped, and flagged via `is_orphan_trip` — that's the DQ signal PROJECT_PLAN.md §9
   describes, not swept under the rug.

   A second, real quirk found the same way: TfNSW's v2 feed leaves `trip.start_date`
   empty on every record in this feed (confirmed empirically, not assumed) — so
   `service_date` falls back to the poll's `feed_timestamp` date wherever start_date
   is blank, rather than silently producing a null service_date downstream.
3. Cross-check — TfNSW's feed already publishes `arrival_delay_seconds` directly, so
   Silver doesn't need to recompute delay from scratch. It does add a plausibility
   range flag (`is_delay_outlier`) since the very first live pull surfaced a real
   5,306-second (~88 min) outlier — exactly the kind of value that needs flagging, not
   silently trusting.
"""

import logging
import sys

from databricks_upload import connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CATALOG = "workspace"

# Delay values outside this range are kept but flagged, not dropped — see
# PROJECT_PLAN.md §9 (quarantine, don't silently drop).
PLAUSIBLE_DELAY_SECONDS = (-600, 7200)


def build_trip_stop_performance(cur) -> None:
    low, high = PLAUSIBLE_DELAY_SECONDS
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.silver.trip_stop_performance AS
        WITH latest_snapshot AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY trip_id, stop_id, stop_sequence
                    ORDER BY _ingested_at DESC
                ) AS rn
            FROM {CATALOG}.bronze.gtfs_rt_trip_updates
        )
        SELECT
            rt.trip_id,
            rt.route_id,
            rt.stop_id,
            rt.stop_sequence,
            COALESCE(NULLIF(rt.start_date, ''), date_format(rt.feed_timestamp, 'yyyyMMdd')) AS service_date,
            rt.schedule_relationship,
            rt.arrival_delay_seconds,
            rt.departure_delay_seconds,
            st.arrival_time AS scheduled_arrival_time_of_day,
            st.departure_time AS scheduled_departure_time_of_day,
            t.trip_headsign,
            t.service_id,
            (t.trip_id IS NULL) AS is_orphan_trip,
            (
                rt.arrival_delay_seconds < {low}
                OR rt.arrival_delay_seconds > {high}
            ) AS is_delay_outlier,
            rt.feed_timestamp,
            rt._ingested_at
        FROM latest_snapshot rt
        LEFT JOIN {CATALOG}.bronze.gtfs_static_trips t
            ON rt.trip_id = t.trip_id
        LEFT JOIN {CATALOG}.bronze.gtfs_static_stop_times st
            ON rt.trip_id = st.trip_id AND rt.stop_sequence = st.stop_sequence
        WHERE rt.rn = 1
        """
    )


def main() -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(f"USE CATALOG {CATALOG}")
        build_trip_stop_performance(cur)

        cur.execute(
            f"""
            SELECT
                count(*) AS total_rows,
                sum(int(is_orphan_trip)) AS orphan_rows,
                sum(int(is_delay_outlier)) AS outlier_rows,
                round(avg(arrival_delay_seconds), 1) AS avg_arrival_delay_seconds,
                min(arrival_delay_seconds) AS min_arrival_delay_seconds,
                max(arrival_delay_seconds) AS max_arrival_delay_seconds
            FROM {CATALOG}.silver.trip_stop_performance
            """
        )
        row = cur.fetchone()
        log.info(
            "silver.trip_stop_performance: %d rows | %d orphan trip_id | "
            "%d delay outliers | avg delay %.1fs | range [%s, %s]",
            row.total_rows,
            row.orphan_rows,
            row.outlier_rows,
            row.avg_arrival_delay_seconds or 0.0,
            row.min_arrival_delay_seconds,
            row.max_arrival_delay_seconds,
        )
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
