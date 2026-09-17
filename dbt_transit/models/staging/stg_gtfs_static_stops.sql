select
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    parent_station
from {{ source('bronze', 'gtfs_static_stops') }}
