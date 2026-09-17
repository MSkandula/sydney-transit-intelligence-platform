"""Small, secondary ML component (see PROJECT_PLAN.md §13 — deliberately not the
focus of this project). Predicts whether a trip-stop will be delayed beyond
TfNSW's own on-time threshold, using features already sitting in Gold:
route, mode, hour of day, day of week, and whether a service alert was active
for that route at that moment (a feature that only exists because of the
alert-delay-impact work already done).

Runs as a standalone script, not a Databricks notebook — same reason as the rest
of this project: the token driving this is scoped to SQL only, so training happens
locally (via a small pandas DataFrame pulled over the SQL connector) rather than
in PySpark. The dataset here (tens of thousands of rows) is comfortably small
enough for that to be the right call, not a workaround.

Real class imbalance in this data (~5.6% of trip-stops are late) — class_weight=
'balanced' and precision/recall/F1/ROC-AUC are used throughout; accuracy alone
would be misleadingly high on this data (predicting "never late" gets ~94%).
"""

import logging
import sys
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from databricks_upload import connect, upload_to_volume  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CATALOG = "workspace"
LOCAL_DIR = Path(__file__).resolve().parent / "scored_output"

TRAINING_QUERY = f"""
    SELECT
        f.trip_id,
        f.stop_id,
        f.service_date,
        f.feed_timestamp,
        r.route_short_name,
        r.mode,
        hour(f.feed_timestamp) AS hour_of_day,
        dayofweek(f.feed_timestamp) AS day_of_week_num,
        EXISTS (
            SELECT 1 FROM {CATALOG}.gold.fact_service_alerts a
            WHERE a.route_key = f.route_key
              AND a.active_period_start IS NOT NULL
              AND f.feed_timestamp BETWEEN a.active_period_start AND a.active_period_end
        ) AS had_active_alert,
        f.is_late
    FROM {CATALOG}.gold.fact_trip_stop_performance f
    JOIN {CATALOG}.gold.dim_route r ON f.route_key = r.route_key
    WHERE NOT f.is_orphan_trip AND f.is_late IS NOT NULL
"""

NUMERIC_FEATURES = ["hour_of_day", "day_of_week_num", "had_active_alert"]
CATEGORICAL_FEATURES = ["route_short_name", "mode"]


def load_training_data(cur) -> pd.DataFrame:
    cur.execute(TRAINING_QUERY)
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=columns)
    df["had_active_alert"] = df["had_active_alert"].astype(int)
    df["is_late"] = df["is_late"].astype(int)
    return df


def temporal_split(df: pd.DataFrame):
    """Train on the earliest service_date(s), test on the latest — predicting
    a future day from past days, not a random shuffle. Falls back to a random
    80/20 split (with a warning) if only one service_date exists yet."""
    dates = sorted(df["service_date"].unique())
    if len(dates) < 2:
        log.warning(
            "Only one service_date (%s) in the data — falling back to a random "
            "80/20 split. Re-run once a second day has accumulated for a real "
            "temporal evaluation.",
            dates,
        )
        test = df.sample(frac=0.2, random_state=42)
        train = df.drop(test.index)
        return train, test

    test_date = dates[-1]
    train = df[df["service_date"] != test_date]
    test = df[df["service_date"] == test_date]
    log.info("Train on %s, test on %s (%d / %d rows)", dates[:-1], test_date, len(train), len(test))
    return train, test


def build_pipeline(model) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline([("preprocess", preprocessor), ("model", model)])


def evaluate(name: str, pipeline: Pipeline, X_test, y_test) -> float:
    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_proba)
    log.info("=== %s ===", name)
    log.info("ROC-AUC: %.3f", auc)
    log.info("\n%s", classification_report(y_test, y_pred, target_names=["on_time", "late"]))
    return auc


def try_log_to_mlflow(best_name: str, best_auc: float, logreg_auc: float, rf_auc: float) -> None:
    """Best-effort MLflow logging via Databricks' managed tracking server. Not
    required for this to be a legitimate small ML component — confirmed (not just
    suspected) that this project's PAT can't do it: Databricks returns
    '403: Provided access token does not have required scopes: mlflow', the exact
    same SQL-only-token pattern as Jobs/Workspace/Files/Unity-Catalog-admin
    elsewhere in this project. Logging the metrics to the pipeline log instead is
    a perfectly fine substitute at this project's scale — a full MLflow registry
    would be over-engineering for one small classifier anyway."""
    try:
        import mlflow

        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment("/Shared/sydney_transit_delay_risk")
        with mlflow.start_run(run_name="delay_risk_model_comparison"):
            mlflow.log_metric("logreg_roc_auc", logreg_auc)
            mlflow.log_metric("random_forest_roc_auc", rf_auc)
            mlflow.log_param("selected_model", best_name)
            mlflow.log_metric("selected_model_roc_auc", best_auc)
        log.info("Logged run to MLflow (Databricks managed tracking).")
    except Exception:
        log.warning(
            "MLflow logging skipped (confirmed: this PAT lacks the 'mlflow' scope, "
            "same pattern as Jobs/Workspace/Files/Unity-Catalog-admin). Metrics are "
            "already in the log above via evaluate() — good enough at this scale.",
            exc_info=True,
        )


def score_and_upload(cur, pipeline: Pipeline, df: pd.DataFrame, model_name: str) -> None:
    scored = df[["trip_id", "stop_id", "service_date"]].copy()
    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    scored["predicted_delay_risk"] = pipeline.predict_proba(df[feature_cols])[:, 1]
    scored["actual_is_late"] = df["is_late"]
    scored["model_name"] = model_name

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LOCAL_DIR / "trip_delay_risk_score.parquet"
    scored.to_parquet(out_path, index=False)

    remote_path = upload_to_volume(out_path, f"ml/{out_path.name}")
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.mart_trip_delay_risk_score AS
        SELECT * FROM read_files('{remote_path}', format => 'parquet')
        """
    )
    cur.execute(f"SELECT count(*) FROM {CATALOG}.gold.mart_trip_delay_risk_score")
    log.info("gold.mart_trip_delay_risk_score: %d rows scored", cur.fetchone()[0])


def main() -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        df = load_training_data(cur)
        log.info(
            "Loaded %d rows | late rate: %.1f%%", len(df), 100 * df["is_late"].mean()
        )

        train, test = temporal_split(df)
        X_train = train[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
        y_train = train["is_late"]
        X_test = test[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
        y_test = test["is_late"]

        logreg = build_pipeline(LogisticRegression(class_weight="balanced", max_iter=1000))
        logreg.fit(X_train, y_train)
        logreg_auc = evaluate("Logistic Regression", logreg, X_test, y_test)

        rf = build_pipeline(
            RandomForestClassifier(
                n_estimators=200, class_weight="balanced", random_state=42, n_jobs=-1
            )
        )
        rf.fit(X_train, y_train)
        rf_auc = evaluate("Random Forest", rf, X_test, y_test)

        if rf_auc >= logreg_auc:
            best_name, best_pipeline, best_auc = "random_forest", rf, rf_auc
        else:
            best_name, best_pipeline, best_auc = "logistic_regression", logreg, logreg_auc
        log.info("Selected model: %s (ROC-AUC %.3f)", best_name, best_auc)

        try_log_to_mlflow(best_name, best_auc, logreg_auc, rf_auc)
        score_and_upload(cur, best_pipeline, df, best_name)

        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
