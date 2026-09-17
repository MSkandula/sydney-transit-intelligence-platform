# Gold Layer Data Model — Star Schema

Reference doc for the Gold layer. Built incrementally: Phase 1 ships a minimal subset
by hand in SQL; Phase 3 rebuilds this fully in dbt. Update this file first when the
model changes — it's the contract between Silver and Gold, and between Gold and Tableau.

## Dimension tables

### `dim_date`
Grain: one row per calendar date.
| Column | Notes |
|---|---|
| `date_key` (PK) | surrogate, e.g. `20260916` |
| `full_date` | |
| `day_of_week`, `is_weekday` | |
| `service_date` | GTFS service date (can differ from calendar date for post-midnight trips) |

### `dim_route`
Grain: one row per route.
| Column | Notes |
|---|---|
| `route_key` (PK) | surrogate |
| `route_id` (natural key) | from GTFS static |
| `route_short_name` | |
| `mode` | train / bus / ferry / light rail |
| `operator` | |

### `dim_stop`
Grain: one row per stop.
| Column | Notes |
|---|---|
| `stop_key` (PK) | surrogate |
| `stop_id` (natural key) | |
| `stop_name`, `suburb` | |
| `lat`, `long` | |
| `parent_station` | for interchange grouping |

### `dim_trip`
Grain: one row per scheduled trip (per static feed version).
| Column | Notes |
|---|---|
| `trip_key` (PK) | surrogate |
| `trip_id` (natural key) | |
| `route_key` (FK) | |
| `direction`, `headsign`, `service_id` | |
| `static_feed_version` | ties the trip to the schedule version it belongs to — see PROJECT_PLAN §6 on RT/static version reconciliation |

## Fact tables

### `fact_trip_stop_performance`
**Grain: one row per scheduled trip visiting one stop on one service date.**
This is the core reliability fact — everything else in the platform exists to explain
or aggregate this table.

| Column | Notes |
|---|---|
| `date_key` (FK) | |
| `route_key` (FK) | |
| `stop_key` (FK) | |
| `trip_key` (FK) | |
| `stop_sequence` | position of this stop within the trip |
| `scheduled_arrival_ts` / `actual_arrival_ts` | |
| `arrival_delay_seconds` | `actual - scheduled` |
| `scheduled_departure_ts` / `actual_departure_ts` | |
| `departure_delay_seconds` | |
| `is_cancelled`, `is_skipped` | |

dbt incremental config (Phase 3): `unique_key = (service_date, trip_id, stop_sequence)`.

### `fact_service_alerts`
Grain: one row per (alert, route) — built as `SELECT DISTINCT` over
`bronze.gtfs_service_alerts`, since the same alert is re-captured on every poll
while it's active. Scoped to route-level alerts for now (`WHERE route_id IS NOT
NULL`); stop-level alerts exist in Bronze but aren't modelled in Gold yet.
| Column | Notes |
|---|---|
| `alert_id` (natural key, from GTFS-RT entity id) | |
| `route_id`, `route_key` (FK to `dim_route`) | |
| `cause`, `effect` | from GTFS-RT alert enums — TfNSW leaves these `UNKNOWN_CAUSE`/`UNKNOWN_EFFECT` on ~half the feed (open-ended station notices), not populated on all alerts |
| `header_text`, `description_text` | human-readable, genuinely useful for a dashboard tooltip |
| `active_period_start`, `active_period_end` | `active_period_end` is null on ~half the feed (open-ended notices) — `mart_alert_delay_impact` only uses alerts where both are present |

## Pre-aggregated marts (Tableau-facing)

### `mart_route_daily_performance`
Grain: route × date. `pct_on_time`, `avg_delay_seconds`, `cancellation_count`,
`trip_count`.

### `mart_stop_daily_performance`
Grain: stop × date. Same measure pattern as above, at stop grain.

### `mart_line_delay_concentration`
Grain: one row per line (`route_short_name`), across all accumulated history —
not date-partitioned, since the point is "which lines matter most overall," not a
daily snapshot. `total_delay_minutes` sums only positive delay
(`greatest(arrival_delay_seconds, 0)`) so early arrivals don't offset lateness
elsewhere. `pct_of_network_delay` and `cumulative_pct_of_network_delay` (rows
pre-sorted worst-first) turn this into a ready-made Pareto chart — the headline
business-impact finding for this project, recomputed automatically every pipeline
run as more history accumulates. See README.md for the current numbers.

### `mart_alert_delay_impact`
Grain: one row per (route, alert). Answers PROJECT_PLAN.md §3's question directly:
does an active disruption alert correlate with a measurable delay spike, or is
impact overstated/understated? `avg_delay_during_alert_seconds` is that route's
average delay while the alert's `active_period` window was open;
`baseline_avg_delay_seconds` is that route's overall average across all history;
`delay_lift_seconds` is the difference. Only computed for alerts with both a start
and end time — see `fact_service_alerts` above for why roughly half don't qualify.

---

## Design notes

- Surrogate keys are generated in dbt (`dbt_utils.generate_surrogate_key` or
  equivalent); natural keys (`route_id`, `stop_id`, `trip_id`) are retained as
  degenerate columns on every table for traceability back to the raw GTFS feeds when
  debugging a join.
- `dim_trip` carries `static_feed_version` because GTFS-RT `trip_id`s are only
  meaningful against the static schedule version that was active on that service date —
  reconciling this correctly in Silver is one of the more genuine data engineering
  problems in this project (see PROJECT_PLAN.md §6).
