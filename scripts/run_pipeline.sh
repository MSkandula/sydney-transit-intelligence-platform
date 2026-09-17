#!/bin/bash
# Runs the full realtime ingestion + Bronze/Silver/Gold pipeline once.
# Invoked on a schedule by ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist
# (see docs/scheduled_ingestion.md) — every run appends one more realtime snapshot,
# which is what actually accumulates the history a trend analysis needs.
#
# Deliberately not re-running gtfs_static_ingest.py on every tick — the static
# schedule only changes ~weekly (see PROJECT_PLAN.md §10); re-fetching it every
# 15 minutes would be wasteful and pointless.

set -uo pipefail

PROJECT_DIR="/Users/maheshkandula/Desktop/sydney-transit-intelligence-platform"
LOG_FILE="$PROJECT_DIR/logs/pipeline.log"

cd "$PROJECT_DIR" || exit 1
source .venv/bin/activate

echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) =====" >> "$LOG_FILE"

python ingestion/gtfs_rt_ingest.py >> "$LOG_FILE" 2>&1
python ingestion/land_bronze.py >> "$LOG_FILE" 2>&1
python ingestion/build_silver.py >> "$LOG_FILE" 2>&1
python ingestion/build_gold.py >> "$LOG_FILE" 2>&1
python ingestion/export_gold_extracts.py >> "$LOG_FILE" 2>&1

echo "===== done $(date -u +%Y-%m-%dT%H:%M:%SZ) =====" >> "$LOG_FILE"
