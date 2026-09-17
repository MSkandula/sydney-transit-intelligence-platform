select
    trip_id,
    route_id,
    service_id,
    trip_headsign
from {{ source('bronze', 'gtfs_static_trips') }}
