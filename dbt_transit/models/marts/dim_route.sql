select
    xxhash64(route_id) as route_key,
    route_id,
    route_short_name,
    route_long_name,
    case route_type
        when 2 then 'train'
        when 3 then 'bus'
        when 4 then 'ferry'
        when 0 then 'light_rail'
        else 'other'
    end as mode,
    agency_id as operator
from {{ ref('stg_gtfs_static_routes') }}
