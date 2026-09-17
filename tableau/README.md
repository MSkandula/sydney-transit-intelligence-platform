# tableau/

Tableau Public workbooks (`.twbx`) and the Gold-layer extracts they're built from.

Tableau Public has no live connector to Databricks — extracts are exported from Gold
marts and refreshed on a documented cadence (see PROJECT_PLAN.md §12 for why, and how
to talk about that trade-off in an interview).

Dashboards (Phase 4): Network Reliability Overview, Route & Stop Deep Dive,
Service Alerts & Impact, and optionally a Pipeline Health tab.

## Published

- **Network Reliability Overview** — [live on Tableau Public](https://public.tableau.com/app/profile/mahesh.sai.kandula7753/viz/SydneyTrains-NetworkReliability/NetworkReliabilityOverview).
  Two views built from `extracts/mart_route_daily_performance.csv`: on-time % by
  route (red→green diverging, worst at top) and average delay in minutes by route
  (sequential red, worst at top). Snapshot dashboard for 2026-09-16 — no trend line
  yet since only one day of realtime data has been captured so far (see ROADMAP.md).
