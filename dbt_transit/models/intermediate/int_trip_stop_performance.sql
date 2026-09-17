-- Reconciliation + dedup, ported from ingestion/build_silver.py (the Phase 1
-- hand-written SQL equivalent). Same three things this step does that Bronze
-- deliberately doesn't:
--
-- 1. Dedup — a trip-stop is reported many times before it's actually reached; keep
--    only the latest snapshot per (service_date, trip_id, stop_id, stop_sequence).
--    service_date is part of the key deliberately: Sydney Trains reuses trip_id
--    across different calendar days, so partitioning without service_date silently
--    collapsed 188 legitimate rows the moment a second day of data existed — a real
--    bug caught in Phase 1, not a hypothetical (see ROADMAP.md).
-- 2. Reconcile — join the RT trip_id against the static schedule it references.
--    98.1% matched directly on trip_id in the first live pull; the rest are kept
--    (left join) and flagged via is_orphan_trip, not dropped.
-- 3. Cross-check — TfNSW already publishes arrival_delay_seconds; this only adds a
--    plausibility flag (is_delay_outlier), never silently drops an extreme value.
--
-- Also replicates the service_date fallback for TfNSW's v2 feed leaving
-- trip.start_date empty on every record (confirmed empirically in Phase 1).

with bronze_with_service_date as (
    select
        *,
        coalesce(nullif(start_date, ''), date_format(feed_timestamp, 'yyyyMMdd'))
            as service_date
    from {{ ref('stg_gtfs_rt_trip_updates') }}
),

latest_snapshot as (
    select
        *,
        row_number() over (
            partition by service_date, trip_id, stop_id, stop_sequence
            order by _ingested_at desc
        ) as rn
    from bronze_with_service_date
)

select
    rt.trip_id,
    rt.route_id,
    rt.stop_id,
    rt.stop_sequence,
    rt.service_date,
    rt.schedule_relationship,
    rt.arrival_delay_seconds,
    rt.departure_delay_seconds,
    st.arrival_time as scheduled_arrival_time_of_day,
    st.departure_time as scheduled_departure_time_of_day,
    t.trip_headsign,
    t.service_id,
    (t.trip_id is null) as is_orphan_trip,
    (
        rt.arrival_delay_seconds < {{ var('plausible_delay_low_seconds') }}
        or rt.arrival_delay_seconds > {{ var('plausible_delay_high_seconds') }}
    ) as is_delay_outlier,
    rt.feed_timestamp,
    rt._ingested_at
from latest_snapshot rt
left join {{ ref('stg_gtfs_static_trips') }} t
    on rt.trip_id = t.trip_id
left join {{ ref('stg_gtfs_static_stop_times') }} st
    on rt.trip_id = st.trip_id and rt.stop_sequence = st.stop_sequence
where rt.rn = 1
