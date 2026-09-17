# ml/

Small, secondary ML component — see [PROJECT_PLAN.md](../PROJECT_PLAN.md) §13 for
why this is deliberately not the focus of this project.

## What it does

`train_delay_risk_model.py` predicts whether a trip-stop will be delayed beyond
TfNSW's own on-time threshold, using features already sitting in Gold: route,
mode, hour of day, day of week, and whether a service alert was active for that
route at that moment (a feature that only exists because of the alert-delay-impact
work already done — see `gold.mart_alert_delay_impact`).

Trains and compares two models (Logistic Regression, Random Forest), picks the
better one by ROC-AUC, and writes scored predictions to
`gold.mart_trip_delay_risk_score`.

Runs as a standalone script over the SQL connector, not a Databricks
notebook/PySpark — same reason as everywhere else in this project (the token is
scoped to `sql` only), and the dataset (tens of thousands of rows) is comfortably
small enough locally for that to be the right call, not a workaround.

## Run it

```bash
pip install -r ml/requirements.txt
python ml/train_delay_risk_model.py
```

## Real results — reported honestly, not dressed up

On the data available at the time of writing (22,114 trip-stop observations,
train on day 1 / test on day 2 — a temporal split, not a random shuffle):

- **~5.6% of trip-stops are late** — a real class imbalance, handled with
  `class_weight='balanced'` rather than ignored
- **Random Forest: ROC-AUC 0.662** (Logistic Regression: 0.658 — barely different)
- **Precision/recall on the "late" class: ~0.13 / ~0.14** — the model is only
  slightly better than chance at actually identifying which specific trip-stops
  will be late

This is a **weak model**, and that's stated plainly rather than glossed over. It's
an honest, expected result given the inputs: only 2 days of training data, and a
small feature set (route/time/alert-flag) that doesn't capture the real drivers of
delay — track incidents, weather, rolling-stock issues, upstream network
congestion — none of which are in this feed. The value of this component isn't
"a production-ready delay predictor"; it's demonstrating the full ML workflow
(feature engineering from a real lakehouse, a fair train/test split, class
imbalance handling, honest multi-metric evaluation, scoring results back into the
warehouse) end to end, and knowing not to oversell a weak result — which is itself
a real, interview-relevant skill.

Re-running `train_delay_risk_model.py` as more days of history accumulate (via the
scheduled pipeline) should improve this meaningfully — 2 days is a genuinely small
sample for a rare, noisy event like "was this specific trip-stop late."

## MLflow — confirmed unavailable, not silently skipped

The script attempts to log run metrics to Databricks' managed MLflow tracking
server, and fails with `403: Provided access token does not have required scopes:
mlflow` — the exact same SQL-only-token pattern documented for Jobs/Workspace/
Files/Unity-Catalog-admin elsewhere in this project (PROJECT_PLAN.md §5). This is
confirmed by actually trying it with `mlflow` installed, not assumed from the
pattern. Metrics are logged to the script's own log output instead — a full MLflow
registry would be over-engineering for one small classifier at this project's
scale anyway.
