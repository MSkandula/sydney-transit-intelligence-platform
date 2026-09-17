-- Incremental. Grain is (service_date, trip_id, stop_id, stop_sequence), NOT just
-- (service_date, trip_id, stop_sequence) as originally documented in
-- PROJECT_PLAN.md §10 — that spec assumed GTFS's usual guarantee that
-- stop_sequence is unique per trip. Real accumulated data broke that assumption:
-- TfNSW's v2 feed reports stop_sequence=0 for *every* stop on at least some
-- NSW TrainLink intercity/regional trips (e.g. a Central Coast & Newcastle Line
-- service with 34 distinct real stations, all stamped stop_sequence=0) — an
-- upstream data quality issue, not a bug in this pipeline. A dbt uniqueness test
-- caught 1,348 violating rows on the first real build; stop_id disambiguates
-- correctly for both well-behaved and broken trips, matching the grain
-- int_trip_stop_performance's own (already-passing) test already uses.
{{ config(
    materialized='incremental',
    unique_key=['service_date', 'trip_id', 'stop_id', 'stop_sequence'],
    incremental_strategy='merge'
) }}

select
    try_cast(s.service_date as int) as date_key,
    s.service_date,
    xxhash64(s.route_id) as route_key,
    xxhash64(s.stop_id) as stop_key,
    s.stop_id,
    s.trip_id,
    s.stop_sequence,
    s.schedule_relationship,
    s.arrival_delay_seconds,
    s.departure_delay_seconds,
    (s.arrival_delay_seconds > {{ var('on_time_threshold_seconds') }}) as is_late,
    (s.schedule_relationship = 'CANCELED') as is_cancelled,
    s.is_orphan_trip,
    s.is_delay_outlier,
    s.feed_timestamp,
    s._ingested_at
from {{ ref('int_trip_stop_performance') }} s
{% if is_incremental() %}
where s._ingested_at > (select max(_ingested_at) from {{ this }})
{% endif %}
