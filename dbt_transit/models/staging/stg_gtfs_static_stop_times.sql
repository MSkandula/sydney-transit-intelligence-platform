select
    trip_id,
    stop_id,
    stop_sequence,
    arrival_time,
    departure_time
from {{ source('bronze', 'gtfs_static_stop_times') }}
