select
    entity_id as alert_id,
    cause,
    effect,
    header_text,
    description_text,
    route_id,
    stop_id,
    trip_id,
    active_period_start,
    active_period_end,
    _ingested_at
from {{ source('bronze', 'gtfs_service_alerts') }}
