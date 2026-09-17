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

"$PYTHON" ingestion/gtfs_rt_ingest.py >> "$LOG_FILE" 2>&1
"$PYTHON" ingestion/gtfs_alerts_ingest.py >> "$LOG_FILE" 2>&1
"$PYTHON" ingestion/land_bronze.py >> "$LOG_FILE" 2>&1
"$DBT" build --project-dir "$PROJECT_DIR/dbt_transit" --profiles-dir ~/.dbt >> "$LOG_FILE" 2>&1
"$PYTHON" ingestion/export_gold_extracts.py >> "$LOG_FILE" 2>&1

echo "===== done $(date -u +%Y-%m-%dT%H:%M:%SZ) =====" >> "$LOG_FILE"
