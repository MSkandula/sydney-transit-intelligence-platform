select
    entity_id,
    trip_id,
    route_id,
    start_date,
    schedule_relationship,
    stop_id,
    stop_sequence,
    arrival_delay_seconds,
    arrival_time,
    departure_delay_seconds,
    departure_time,
    stop_schedule_relationship,
    feed_timestamp,
    _ingested_at
from {{ source('bronze', 'gtfs_rt_trip_updates') }}
