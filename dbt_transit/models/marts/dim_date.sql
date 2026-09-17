with calendar_bounds as (
    select
        min(start_date) as min_date,
        max(end_date) as max_date
    from {{ ref('stg_gtfs_static_calendar') }}
)

select
    int(date_format(d, 'yyyyMMdd')) as date_key,
    d as full_date,
    date_format(d, 'EEEE') as day_of_week,
    (dayofweek(d) not in (1, 7)) as is_weekday
from (
    select explode(sequence(
        to_date(string(min_date), 'yyyyMMdd'),
        to_date(string(max_date), 'yyyyMMdd'),
        interval 1 day
    )) as d
    from calendar_bounds
)
