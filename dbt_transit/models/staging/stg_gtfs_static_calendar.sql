-- Bronze keeps every timetable version (TfNSW rotates trip IDs, so old live data can only
-- be reconciled against the version that was current at the time). Staging exposes one
-- row per service_id, taking the newest version when a key appears in several.
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
qualify row_number() over (
    partition by service_id
    order by _ingested_at desc, _feed_version desc
) = 1
