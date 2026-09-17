# KPI definitions

The precise definition of every metric used in the Tableau dashboards and the
business-impact findings in README.md. Where a definition matches an external
standard (TfNSW's own), that's stated explicitly — these numbers are meant to mean
what a stakeholder would assume they mean, not an arbitrary convenience threshold.

## On-time / punctuality

**On-time (`is_late = false`)**: a trip-stop's `arrival_delay_seconds ≤ 300`
(5 minutes). This matches TfNSW's own published "Customer On-Time" standard for
Sydney Trains — verified against transport.nsw.gov.au, not assumed or
misremembered (an earlier draft of this project used an incorrect 5:59 threshold,
corrected before shipping — see ROADMAP.md).

**% On-Time (`pct_on_time`)**: `100 × (trip-stops with is_late = false) / (total
trip-stops)`, computed per route per date in `gold.mart_route_daily_performance`.
Excludes orphan trips (see below) — an unreconciled trip-stop has no verified
relationship to the schedule it's being judged against.

**Average delay (`avg_arrival_delay_seconds`)**: mean of `arrival_delay_seconds`
across all (non-orphan) trip-stops for a route/date. Includes early arrivals as
negative values — this is a genuine average, not a "how late when late" figure.

## Orphan trips and delay outliers — flags, not filters

**Orphan trip (`is_orphan_trip`)**: a realtime trip-stop update whose `trip_id`
doesn't match any trip in the current static schedule. Empirically ~1.9% of
realtime records in the first live pull (98.1% matched directly). Kept in Silver
and Gold, excluded only from performance aggregates (`mart_route_daily_performance`,
`mart_line_delay_concentration`) where "which route was this" needs to be known —
never silently dropped from the fact table itself.

**Delay outlier (`is_delay_outlier`)**: `arrival_delay_seconds < -600` or `> 7200`
(i.e. more than 10 min early or 2 hours late). A plausibility flag, not a filter —
the first live pull already surfaced a genuine 5,306-second (~88 min) delay that
sits *inside* this range, a reminder that the threshold itself may need revisiting
as more data accumulates, not that outliers should be trusted blindly either way.

## Business-impact metrics

**Total delay-minutes (`total_delay_minutes`, in `mart_line_delay_concentration`)**:
sum of `greatest(arrival_delay_seconds, 0)` per line, converted to minutes. Uses
*positive* delay only — an early arrival on one trip doesn't offset a late arrival
on another when the question is "where is operational attention actually needed."

**% of network delay (`pct_of_network_delay`)**: a line's `total_delay_seconds`
as a share of the sum across all lines. **Cumulative %
(`cumulative_pct_of_network_delay`)**: running total ordered worst-to-best — this
is what turns the mart into a ready-made Pareto chart.

**Delay lift (`delay_lift_seconds`, in `mart_alert_delay_impact`)**:
`avg_delay_during_alert_seconds − baseline_avg_delay_seconds` for a given
route/alert pair. Positive means the route ran worse while the alert was active
than its own long-run average; negative means better. Only computed for alerts
with both a start and end time (roughly half the feed — see
[docs/data_model.md](data_model.md) for why the rest are excluded rather than
silently merged in with an assumed window).

## ML risk score

**Predicted delay risk (`predicted_delay_risk`, in `gold.mart_trip_delay_risk_score`)**:
a classifier's predicted probability that a trip-stop's `is_late` is 1, from
`ml/train_delay_risk_model.py`. **Not a validated production signal** — current
ROC-AUC is ~0.66 with weak precision/recall on the minority class, reported
plainly in [ml/README.md](../ml/README.md) rather than dressed up. Treat as a
demonstration of the workflow, not an operational tool, until it's retrained on
meaningfully more history.

## Data freshness

**Source freshness** (`dbt source freshness`): `gtfs_rt_trip_updates` and
`gtfs_service_alerts` are expected to have a row within the last 30 minutes (warn)
/ 90 minutes (error), sized around the 15-minute scheduled poll interval. Run as a
non-blocking diagnostic on every scheduled pipeline tick — see
[docs/scheduled_ingestion.md](scheduled_ingestion.md).
