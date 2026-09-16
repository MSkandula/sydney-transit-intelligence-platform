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
Grain: one row per alert × affected route/stop × active period.
| Column | Notes |
|---|---|
| `alert_key` (PK) | |
| `route_key` (FK, nullable) | alert may be route-specific |
| `stop_key` (FK, nullable) | or stop-specific |
| `date_key` (FK) | |
| `cause`, `effect`, `severity` | from GTFS-RT alert enums |
| `active_start_ts`, `active_end_ts` | |

## Pre-aggregated marts (Tableau-facing)

### `mart_route_daily_performance`
Grain: route × date. `pct_on_time`, `avg_delay_seconds`, `cancellation_count`,
`trip_count`.

### `mart_stop_daily_performance`
Grain: stop × date. Same measure pattern as above, at stop grain.

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
