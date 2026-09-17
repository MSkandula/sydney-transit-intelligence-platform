select
    service_id,
    monday,
    tuesday,
    wednesday,
    thursday,
    friday,
    saturday,
    sunday,
    start_date,
    end_date
from {{ source('bronze', 'gtfs_static_calendar') }}
