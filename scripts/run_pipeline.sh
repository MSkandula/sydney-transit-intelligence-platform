#!/bin/bash
# Runs the full realtime ingestion + Bronze/Silver/Gold pipeline once.
# Invoked on a schedule by ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist
# (see docs/scheduled_ingestion.md) — every run appends one more realtime snapshot,
# which is what actually accumulates the history a trend analysis needs.
#
# Deliberately not re-running gtfs_static_ingest.py on every tick — the static
# schedule only changes ~weekly (see PROJECT_PLAN.md §10); re-fetching it every
# 15 minutes would be wasteful and pointless.
#
# Silver/Gold run via dbt (dbt_transit/), not ingestion/build_silver.py +
# build_gold.py — those were the Phase 1 hand-written equivalent, superseded once
# dbt_transit/ was built in Phase 3. Both write to the same silver/gold schemas, so
# only one may run against them at a time — running both would corrupt each other's
# table schemas (this happened once during the cutover; see dbt_transit/README.md).

set -uo pipefail

PROJECT_DIR="/Users/maheshkandula/sydney-transit-intelligence-platform"
LOG_FILE="$PROJECT_DIR/logs/pipeline.log"
# launchd runs scripts with a minimal PATH that doesn't reliably pick up
# `source .venv/bin/activate` — call the venv's own binaries directly instead.
PYTHON="$PROJECT_DIR/.venv/bin/python"
DBT="$PROJECT_DIR/.venv/bin/dbt"

cd "$PROJECT_DIR" || exit 1
set -a; source .env; set +a

echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) =====" >> "$LOG_FILE"

# A failed step must be visible: earlier versions printed "done" no matter what, so a
# crashing Bronze load went unnoticed for weeks. Each step's failure is recorded, the
# final line says OK or FAILED, and the script's exit code (shown by `launchctl list`)
# is non-zero if anything failed.
FAILED_STEPS=""
run_step() {
  local name="$1"; shift
  "$@" >> "$LOG_FILE" 2>&1 || { FAILED_STEPS="$FAILED_STEPS $name"; echo "!!! step failed: $name" >> "$LOG_FILE"; }
}

# The static timetable is refreshed at most once a day. It was originally fetched once and
# never again; when TfNSW rotated its trip IDs a few days later, every live trip stopped
# matching the stale timetable and the data silently became ~100% unreconciled.
if ! find "$PROJECT_DIR/data/bronze/gtfs_static/sydneytrains" -name '*.zip' -mtime -1 2>/dev/null | grep -q .; then
  run_step static_ingest "$PYTHON" ingestion/gtfs_static_ingest.py
fi

run_step rt_ingest     "$PYTHON" ingestion/gtfs_rt_ingest.py
run_step alerts_ingest "$PYTHON" ingestion/gtfs_alerts_ingest.py
run_step land_bronze   "$PYTHON" ingestion/land_bronze.py
run_step dbt_build     "$DBT" build --project-dir "$PROJECT_DIR/dbt_transit" --profiles-dir ~/.dbt
# Fails (non-zero) when realtime data is stale, which is what makes a silent ingestion
# outage show up as a failed run instead of a green one.
run_step dbt_freshness "$DBT" source freshness --project-dir "$PROJECT_DIR/dbt_transit" --profiles-dir ~/.dbt
run_step health_check  "$PYTHON" ingestion/check_pipeline_health.py
run_step export_csv    "$PYTHON" ingestion/export_gold_extracts.py

if [ -z "$FAILED_STEPS" ]; then
  echo "===== done OK $(date -u +%Y-%m-%dT%H:%M:%SZ) =====" >> "$LOG_FILE"
  exit 0
fi
echo "===== done FAILED:$FAILED_STEPS $(date -u +%Y-%m-%dT%H:%M:%SZ) =====" >> "$LOG_FILE"
exit 1
