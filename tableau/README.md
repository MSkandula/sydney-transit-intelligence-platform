# tableau/

Tableau Public workbooks (`.twbx`) and the Gold-layer extracts they're built from.

Tableau Public has no live connector to Databricks — extracts are exported from Gold
marts and refreshed on a documented cadence (see PROJECT_PLAN.md §12 for why, and how
to talk about that trade-off in an interview).

Dashboards (Phase 4): Network Reliability Overview, Route & Stop Deep Dive,
Service Alerts & Impact, and optionally a Pipeline Health tab.

## Published

Both dashboards below live in the same Tableau Public workbook
(`SydneyTrains-NetworkReliability`), each with its own shareable URL.

- **Network Reliability Overview** — [live](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/NetworkReliabilityOverview).
  Two views built from `extracts/mart_route_daily_performance.csv`: on-time % by
  route (red→green diverging, worst at top) and average delay in minutes by route
  (sequential red, worst at top).

  ![Network Reliability Overview](screenshots/network_reliability_overview.png)

- **Business Impact** — [live](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/BusinessImpact).
  A Pareto chart (`extracts/mart_line_delay_concentration.csv`: bars for delay
  minutes + a dual-axis cumulative % line) and a diverging bar chart
  (`extracts/mart_alert_delay_impact.csv`: which alerts correlate with a real
  measured delay lift vs. baseline, colored red=worse/green=better).

  ![Business Impact — Pareto chart](screenshots/business_impact.png)

Screenshots are Tableau Public's own auto-generated preview thumbnails (fetched from
each viz's `og:image`), not manual captures — they'll go stale as the underlying data
grows; re-fetch them after a significant republish if that matters for a specific
purpose (e.g. before sending someone the repo directly rather than the live links).

Both grow more meaningful as `scripts/run_pipeline.sh` accumulates more history —
see ROADMAP.md for current row counts, which will be out of date by the time you
read this (that's expected; re-run `export_gold_extracts.py` for current numbers).
