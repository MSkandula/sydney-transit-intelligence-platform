select
    route_id,
    route_short_name,
    route_long_name,
    route_type,
    agency_id,
    _feed_version,
    _ingested_at
from {{ source('bronze', 'gtfs_static_routes') }}
