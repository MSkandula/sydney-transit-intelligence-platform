-- Route-level alerts only for now (WHERE route_id is not null) — stop-level alerts
-- exist in Bronze but aren't modelled here yet. DISTINCT because the same alert is
-- re-captured on every poll while it's active.
select distinct
    alert_id,
    cause,
    effect,
    header_text,
    description_text,
    route_id,
    xxhash64(route_id) as route_key,
    active_period_start,
    active_period_end
from {{ ref('stg_gtfs_service_alerts') }}
where route_id is not null and route_id != ''
