"""Build the Phase 1 Gold layer: a minimal but real star schema over Silver.

Hand-written SQL, deliberately — dbt takes over this layer in Phase 3 (see
dbt_transit/). The point of Phase 1 is proving the pipeline and the model shape
work end to end before adding dbt's testing/docs machinery on top.

Tables built here (grain documented in docs/data_model.md):
- gold.dim_date         one row per calendar date across the current static feed's
                        service period
- gold.dim_route        one row per route (from gtfs_static_routes)
- gold.dim_stop         one row per stop (from gtfs_static_stops)
- gold.fact_trip_stop_performance   grain: one row per trip-stop event, from Silver,
                        joined to the dims above for surrogate keys
- gold.mart_route_daily_performance  route x date, pre-aggregated for Tableau
- gold.mart_line_delay_concentration  line-level Pareto: what share of total
                        network delay-minutes each line is responsible for —
                        the headline business-impact finding (see README.md)
"""

import logging
import sys

from databricks_upload import connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CATALOG = "workspace"

# TfNSW's published punctuality standard: a Sydney Trains service counts as on-time
# when it arrives within five minutes of the timetable (transport.nsw.gov.au data &
# insights — "New Customer On-Time measure"). Used here instead of an arbitrary
# round number so pct_on_time means what TfNSW itself would call on-time.
ON_TIME_THRESHOLD_SECONDS = 300


def build_dims(cur) -> None:
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.dim_date AS
        SELECT
            int(date_format(d, 'yyyyMMdd')) AS date_key,
            d AS full_date,
            date_format(d, 'EEEE') AS day_of_week,
            (dayofweek(d) NOT IN (1, 7)) AS is_weekday
        FROM (
            SELECT explode(sequence(
                to_date(string(min(start_date)), 'yyyyMMdd'),
                to_date(string(max(end_date)), 'yyyyMMdd'),
                interval 1 day
            )) AS d
            FROM {CATALOG}.bronze.gtfs_static_calendar
        )
        """
    )

    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.dim_route AS
        SELECT
            xxhash64(route_id) AS route_key,
            route_id,
            route_short_name,
            route_long_name,
            CASE route_type
                WHEN 2 THEN 'train'
                WHEN 3 THEN 'bus'
                WHEN 4 THEN 'ferry'
                WHEN 0 THEN 'light_rail'
                ELSE 'other'
            END AS mode,
            agency_id AS operator
        FROM {CATALOG}.bronze.gtfs_static_routes
        """
    )

    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.dim_stop AS
        SELECT
            xxhash64(stop_id) AS stop_key,
            stop_id,
            stop_name,
            stop_lat,
            stop_lon,
            parent_station
        FROM {CATALOG}.bronze.gtfs_static_stops
        """
    )


def build_fact(cur) -> None:
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.fact_trip_stop_performance AS
        SELECT
            try_cast(s.service_date AS INT) AS date_key,
            xxhash64(s.route_id) AS route_key,
            xxhash64(s.stop_id) AS stop_key,
            s.trip_id,
            s.stop_sequence,
            s.schedule_relationship,
            s.arrival_delay_seconds,
            s.departure_delay_seconds,
            (s.arrival_delay_seconds > {ON_TIME_THRESHOLD_SECONDS}) AS is_late,
            (s.schedule_relationship = 'CANCELED') AS is_cancelled,
            s.is_orphan_trip,
            s.is_delay_outlier,
            s.feed_timestamp,
            s._ingested_at
        FROM {CATALOG}.silver.trip_stop_performance s
        """
    )


def build_marts(cur) -> None:
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.mart_route_daily_performance AS
        SELECT
            f.date_key,
            r.route_id,
            r.route_short_name,
            r.mode,
            count(*) AS trip_stop_count,
            sum(int(f.is_late)) AS late_count,
            sum(int(f.is_cancelled)) AS cancelled_count,
            round(100.0 * sum(int(NOT f.is_late)) / count(*), 1) AS pct_on_time,
            round(avg(f.arrival_delay_seconds), 1) AS avg_arrival_delay_seconds
        FROM {CATALOG}.gold.fact_trip_stop_performance f
        JOIN {CATALOG}.gold.dim_route r ON f.route_key = r.route_key
        WHERE NOT f.is_orphan_trip
        GROUP BY f.date_key, r.route_id, r.route_short_name, r.mode
        """
    )

    # Business-impact headline: which lines account for most of the network's total
    # delay-minutes. Uses positive delay only (greatest(...,0)) — early arrivals
    # shouldn't offset lateness elsewhere when the question is "where should
    # operational attention go." Mirrors the concentration framing from the
    # e-commerce project's "top 10% of sellers drive 67.6% of revenue" finding.
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.mart_line_delay_concentration AS
        WITH line_totals AS (
            SELECT
                r.route_short_name,
                r.mode,
                sum(greatest(f.arrival_delay_seconds, 0)) AS total_delay_seconds,
                count(*) AS trip_stop_count
            FROM {CATALOG}.gold.fact_trip_stop_performance f
            JOIN {CATALOG}.gold.dim_route r ON f.route_key = r.route_key
            WHERE NOT f.is_orphan_trip
            GROUP BY r.route_short_name, r.mode
        )
        SELECT
            route_short_name,
            mode,
            total_delay_seconds,
            round(total_delay_seconds / 60, 1) AS total_delay_minutes,
            trip_stop_count,
            round(100.0 * total_delay_seconds / sum(total_delay_seconds) OVER (), 1)
                AS pct_of_network_delay,
            round(
                100.0 * sum(total_delay_seconds) OVER (
                    ORDER BY total_delay_seconds DESC
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) / sum(total_delay_seconds) OVER (),
                1
            ) AS cumulative_pct_of_network_delay
        FROM line_totals
        ORDER BY total_delay_seconds DESC
        """
    )


def main() -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(f"USE CATALOG {CATALOG}")

        build_dims(cur)
        for t in ("dim_date", "dim_route", "dim_stop"):
            cur.execute(f"SELECT count(*) FROM {CATALOG}.gold.{t}")
            log.info("gold.%s: %d rows", t, cur.fetchone()[0])

        build_fact(cur)
        cur.execute(f"SELECT count(*) FROM {CATALOG}.gold.fact_trip_stop_performance")
        log.info("gold.fact_trip_stop_performance: %d rows", cur.fetchone()[0])

        build_marts(cur)
        cur.execute(f"SELECT * FROM {CATALOG}.gold.mart_route_daily_performance ORDER BY pct_on_time LIMIT 10")
        log.info("Worst 10 routes by pct_on_time today:")
        for row in cur.fetchall():
            log.info("  %s", row)

        cur.execute(
            f"SELECT route_short_name, total_delay_minutes, pct_of_network_delay, "
            f"cumulative_pct_of_network_delay FROM {CATALOG}.gold.mart_line_delay_concentration"
        )
        log.info("Delay concentration by line (business-impact headline):")
        for row in cur.fetchall():
            log.info("  %s", row)

        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
