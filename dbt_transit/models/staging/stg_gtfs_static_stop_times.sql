-- Bronze keeps every timetable version (TfNSW rotates trip IDs, so old live data can only
-- be reconciled against the version that was current at the time). Staging exposes one
-- row per trip_id, stop_sequence, taking the newest version when a key appears in several.
select
    trip_id,
    stop_id,
    stop_sequence,
    arrival_time,
    departure_time
from {{ source('bronze', 'gtfs_static_stop_times') }}
qualify row_number() over (
    partition by trip_id, stop_sequence
    order by _ingested_at desc, _feed_version desc
) = 1
