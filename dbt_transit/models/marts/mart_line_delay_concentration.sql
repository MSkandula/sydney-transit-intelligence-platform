-- Business-impact headline (see README.md): which lines account for most of the
-- network's total delay-minutes. Positive delay only (greatest(...,0)) so early
-- arrivals don't offset lateness elsewhere — the question is "where should
-- operational attention go," and a Pareto/concentration framing answers it directly.
with line_totals as (
    select
        r.route_short_name,
        r.mode,
        sum(greatest(f.arrival_delay_seconds, 0)) as total_delay_seconds,
        count(*) as trip_stop_count
    from {{ ref('fact_trip_stop_performance') }} f
    join {{ ref('dim_route') }} r on f.route_key = r.route_key
    where not f.is_orphan_trip
    group by r.route_short_name, r.mode
)

select
    route_short_name,
    mode,
    total_delay_seconds,
    round(total_delay_seconds / 60, 1) as total_delay_minutes,
    trip_stop_count,
    round(100.0 * total_delay_seconds / sum(total_delay_seconds) over (), 1)
        as pct_of_network_delay,
    round(
        100.0 * sum(total_delay_seconds) over (
            order by total_delay_seconds desc
            rows between unbounded preceding and current row
        ) / sum(total_delay_seconds) over (),
        1
    ) as cumulative_pct_of_network_delay
from line_totals
order by total_delay_seconds desc
