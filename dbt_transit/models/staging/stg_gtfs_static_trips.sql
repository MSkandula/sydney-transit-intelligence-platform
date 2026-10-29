-- Bronze keeps every timetable version (TfNSW rotates trip IDs, so old live data can only
-- be reconciled against the version that was current at the time). Staging exposes one
-- row per trip_id, taking the newest version when a key appears in several.
select
    trip_id,
    route_id,
    service_id,
    trip_headsign
from {{ source('bronze', 'gtfs_static_trips') }}
qualify row_number() over (
    partition by trip_id
    order by _ingested_at desc, _feed_version desc
) = 1
