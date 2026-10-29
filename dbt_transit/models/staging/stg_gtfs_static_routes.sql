-- Bronze keeps every timetable version (TfNSW rotates trip IDs, so old live data can only
-- be reconciled against the version that was current at the time). Staging exposes one
-- row per route_id, taking the newest version when a key appears in several.
select
    route_id,
    route_short_name,
    route_long_name,
    route_type,
    agency_id,
    _feed_version,
    _ingested_at
from {{ source('bronze', 'gtfs_static_routes') }}
qualify row_number() over (
    partition by route_id
    order by _ingested_at desc, _feed_version desc
) = 1
