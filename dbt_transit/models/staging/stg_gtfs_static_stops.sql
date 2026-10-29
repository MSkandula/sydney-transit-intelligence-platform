-- Bronze keeps every timetable version (TfNSW rotates trip IDs, so old live data can only
-- be reconciled against the version that was current at the time). Staging exposes one
-- row per stop_id, taking the newest version when a key appears in several.
select
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    parent_station
from {{ source('bronze', 'gtfs_static_stops') }}
qualify row_number() over (
    partition by stop_id
    order by _ingested_at desc, _feed_version desc
) = 1
