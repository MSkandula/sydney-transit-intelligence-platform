select
    f.date_key,
    r.route_id,
    r.route_short_name,
    r.mode,
    count(*) as trip_stop_count,
    sum(int(f.is_late)) as late_count,
    sum(int(f.is_cancelled)) as cancelled_count,
    round(100.0 * sum(int(not f.is_late)) / count(*), 1) as pct_on_time,
    round(avg(f.arrival_delay_seconds), 1) as avg_arrival_delay_seconds
from {{ ref('fact_trip_stop_performance') }} f
join {{ ref('dim_route') }} r on f.route_key = r.route_key
where not f.is_orphan_trip
group by f.date_key, r.route_id, r.route_short_name, r.mode
