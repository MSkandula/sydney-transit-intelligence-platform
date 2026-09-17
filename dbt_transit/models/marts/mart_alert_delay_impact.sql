-- Does a disruption alert actually correlate with measurable delay, or is impact
-- overstated/understated (PROJECT_PLAN.md §3)? Compares each route's average delay
-- *during* an alert's active window against that route's overall baseline. Only
-- alerts with both a start and end time produce a defined window — roughly half the
-- feed is open-ended station notices, excluded rather than silently merged in.
with alert_windows as (
    select distinct
        route_key, route_id, header_text, cause, effect,
        active_period_start, active_period_end
    from {{ ref('fact_service_alerts') }}
    where active_period_start is not null and active_period_end is not null
),

delay_during_alert as (
    select
        a.route_id, a.header_text, a.cause, a.effect,
        avg(f.arrival_delay_seconds) as avg_delay_during_alert,
        count(*) as observations_during_alert
    from alert_windows a
    join {{ ref('fact_trip_stop_performance') }} f
        on f.route_key = a.route_key
        and f.feed_timestamp between a.active_period_start and a.active_period_end
    where not f.is_orphan_trip
    group by a.route_id, a.header_text, a.cause, a.effect
),

baseline as (
    select r.route_id, avg(f.arrival_delay_seconds) as baseline_avg_delay
    from {{ ref('fact_trip_stop_performance') }} f
    join {{ ref('dim_route') }} r on f.route_key = r.route_key
    where not f.is_orphan_trip
    group by r.route_id
)

select
    d.route_id,
    d.header_text,
    d.cause,
    d.effect,
    d.observations_during_alert,
    round(d.avg_delay_during_alert, 1) as avg_delay_during_alert_seconds,
    round(b.baseline_avg_delay, 1) as baseline_avg_delay_seconds,
    round(d.avg_delay_during_alert - b.baseline_avg_delay, 1) as delay_lift_seconds
from delay_during_alert d
join baseline b on d.route_id = b.route_id
order by delay_lift_seconds desc
