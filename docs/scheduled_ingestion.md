# Scheduled ingestion (local launchd job)

Why this exists: a single point-in-time snapshot of realtime data can't support any
trend or business-impact analysis — `gold.mart_line_delay_concentration`'s numbers
get more statistically meaningful the more polls it's built from. This job is what
accumulates that history.

## What it runs

`scripts/run_pipeline.sh` — pulls one fresh realtime snapshot and rebuilds
Bronze → Silver → Gold → Tableau CSV exports:

```
gtfs_rt_ingest.py → land_bronze.py → build_silver.py → build_gold.py → export_gold_extracts.py
```

It deliberately does **not** re-run `gtfs_static_ingest.py` every time — the static
schedule only changes ~weekly (see PROJECT_PLAN.md §10), so re-fetching a 10MB zip
every 15 minutes would be pure waste.

## How it's scheduled

A macOS `launchd` agent — `~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist`
(template checked in at [scripts/com.mahesh.sydney-transit-ingest.plist.example](../scripts/com.mahesh.sydney-transit-ingest.plist.example),
since the real one lives outside the repo per-machine) — runs the script every 900
seconds (15 minutes).

```bash
# copy the template, fill in your username, then:
launchctl load ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist

# check it's running
launchctl list | grep sydney-transit

# stop it
launchctl unload ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist

# watch it work
tail -f logs/pipeline.log
```

### Two real setup problems hit getting this working (both fixed)

1. **`Operation not permitted` in `logs/launchd_stderr.log`.** `~/Desktop`,
   `~/Documents`, and `~/Downloads` are TCC-protected on modern macOS — an
   interactive Terminal has consent to read/write there, but a `launchd` agent is a
   different process identity and doesn't inherit it. The project originally lived
   under `~/Desktop/`; the fix was moving it to `~/sydney-transit-intelligence-platform`
   (unprotected), not granting Full Disk Access to `/bin/bash` (the fragile,
   GUI-dependent alternative). Worth knowing before scheduling *any* background job
   against a project sitting in one of those folders.
2. **`python: command not found` in `logs/pipeline.log`.** `launchd` runs scripts
   with a minimal `PATH` that doesn't reliably pick up `source .venv/bin/activate`.
   Fixed by calling the venv's interpreter directly by absolute path
   (`$PROJECT_DIR/.venv/bin/python`) instead of relying on activation — the standard,
   robust pattern for any cron/launchd-invoked Python script.

## Honest limitations

- **Not 24/7.** launchd only fires while the Mac is awake. This is real accumulated
  history, not a complete continuous record — gaps exist whenever the laptop is
  asleep or off. Worth saying plainly in an interview rather than implying otherwise.
- **Not Databricks Jobs/Workflows.** The project's Databricks personal access token
  is scoped to `sql` only (see PROJECT_PLAN.md §5/§11) — it can't drive the Jobs API,
  so a "real" 24/7 Databricks-native schedule would need to be configured by hand in
  the Databricks UI (a logged-in browser session has full permissions regardless of
  this token's scope). That remains the honest Phase 2 target if continuous coverage
  becomes worth the manual setup.
- **Why 15 minutes, not TfNSW's ~15-second refresh rate:** polling that fast buys no
  real analytical value for a reliability trend and risks Databricks Free Edition's
  fair-usage quota (see PROJECT_PLAN.md §5) — 15 minutes is a deliberate, conservative
  choice, not a limitation to route around.
