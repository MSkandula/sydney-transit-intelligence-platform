select
    xxhash64(stop_id) as stop_key,
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    parent_station
from {{ ref('stg_gtfs_static_stops') }}
