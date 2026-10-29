# Runbook

Operational reference for this project: how to check it's healthy, and what to do
when it isn't. [docs/scheduled_ingestion.md](scheduled_ingestion.md) explains *why*
the schedule is built the way it is; this doc is the "something looks wrong, now
what" companion — the checks and fixes actually used while running this pipeline.

## Quick health check

```bash
# Is the scheduled job loaded and alive?
launchctl list | grep sydney-transit
# -> "<pid>  0  com.mahesh.sydney-transit-ingest" if idle (pid) or between-runs (-)
#    a non-zero second column is the last exit code — investigate if it's not 0

# Did the last run finish cleanly?
grep "^=====" logs/pipeline.log | tail -4
# every "start" line should be followed by a "done" line — a start with no
# matching done means that run either crashed or is still in progress

# Are the three CI/CD workflows green?
gh run list --repo MSkandula/sydney-transit-intelligence-platform --limit 5

# Is realtime data still arriving on schedule?
cd dbt_transit && set -a && source ../.env && set +a
dbt source freshness --project-dir . --profiles-dir ~/.dbt
# warn >30 min stale, error >90 min — see docs/kpi_definitions.md
```

## Common failure modes (all previously hit on this project, all resolved)

| Symptom | Cause | Fix |
|---|---|---|
| `Operation not permitted` in `logs/launchd_stderr.log` | Project sitting under a TCC-protected folder (`~/Desktop`, `~/Documents`, `~/Downloads`) | Move the project outside those folders — see [scheduled_ingestion.md](scheduled_ingestion.md#two-real-setup-problems-hit-getting-this-working-both-fixed) |
| `python: command not found` in `pipeline.log` | `launchd` runs with a minimal `PATH` | `run_pipeline.sh` calls `.venv/bin/python`/`.venv/bin/dbt` by absolute path, not relying on `source activate` |
| `429 RESOURCE_EXHAUSTED` from the Databricks SQL warehouse | Two pipeline runs firing at once (e.g. a manual run overlapping the scheduled one) | Don't manually run `scripts/run_pipeline.sh` within ~15 min of the last scheduled tick; if it happens, it's transient — retry once the other run finishes |
| First query of the day takes ~2 minutes to return | Free Edition's serverless SQL warehouse cold-starts after being idle | Not a failure — wait it out. Avoid tight polling loops on the first query after a gap |
| A `dbt build` test fails that never has before | Either a genuine new TfNSW data quality issue (this has happened 3 times — see [dbt_transit/README.md](../dbt_transit/README.md#real-things-this-projects-first-build-caught)), or a real regression | Read the failing test's compiled SQL (`dbt_transit/target/compiled/...`) before assuming which one it is — don't relax a test to make it pass without checking |
| Pipeline log ends `done FAILED: land_bronze` with `INT64 ... double` | A realtime parquet file was written with integer columns; Bronze expects DOUBLE | `ingestion/gtfs_rt_ingest.py` now pins these columns to float64 (regression test included). To repair old files, rewrite them as float64 and re-upload, see the incident log |
| Health check says `% of trips ... don't match the static timetable` | The static timetable on file is out of date (TfNSW rotated trip IDs) | `python ingestion/gtfs_static_ingest.py` then `python ingestion/land_bronze.py`; the pipeline now does this daily on its own |
| `dbt build --target ci` looks like it passed but dev's tables look different afterward | `generate_schema_name.sql`'s CI branch regressed | Confirm `ci` runs land in the `ci` schema, not `dev`'s `silver`/`gold` — see the macro's own comment for why this matters |
| GitHub Actions `dbt-docs.yml` doesn't trigger after a push | Its `paths: ["dbt_transit/**"]` filter didn't match (e.g. only `README.md` or the workflow file itself changed) | `gh workflow run dbt-docs.yml` to trigger it manually |

## Manual recovery

```bash
# Run the full pipeline by hand (only if the scheduled job isn't about to fire)
./scripts/run_pipeline.sh
tail -f logs/pipeline.log

# Reload the scheduled job after editing its plist or the script
launchctl unload ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist
launchctl load ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist

# Rebuild dbt docs and redeploy without waiting for the next relevant push
gh workflow run dbt-docs.yml --repo MSkandula/sydney-transit-intelligence-platform

# Refresh the Tableau CSV extracts on demand (normally done by the scheduled run)
source .venv/bin/activate && python ingestion/export_gold_extracts.py
```

## Where to look

- **Pipeline log**: `logs/pipeline.log` (gitignored, local only)
- **CI/CD runs**: `gh run list --repo MSkandula/sydney-transit-intelligence-platform`, or the Actions tab on GitHub
- **dbt docs / catalog**: [mskandula.github.io/sydney-transit-intelligence-platform](https://mskandula.github.io/sydney-transit-intelligence-platform/)
- **Live dashboards**: linked in [README.md](../README.md#what%27s-built-and-verified-so-far)

## Starting and stopping the pipeline

It is a scheduled job on a laptop (macOS `launchd`), so it runs only while the Mac is awake.

```bash
launchctl list | grep sydney-transit      # "-  0  ..." = idle and the last run exited 0
launchctl unload ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist   # stop
launchctl load   ~/Library/LaunchAgents/com.mahesh.sydney-transit-ingest.plist   # start (runs once now, then every 15 min)
```

How to explain a gap in the data, truthfully: the collector is a laptop job, so there are no
records while the laptop is asleep or off (for example 10-20 Oct and 26-27 Oct 2026). Restarting
it resumes collection; it cannot backfill the missed period because the realtime feed only shows
the present.

## Incident log

### 2026-10-29: two silent failures, both found and fixed

Both failures looked healthy from the outside: the scheduled job kept running and the log kept
ending with "done". That is itself the third finding, and it is fixed below.

**1. Bronze loading crashed for about 3.5 weeks (from 4 Oct)**
- **Symptom:** no new rows reached Databricks after 4 Oct; `land_bronze.py` raised
  `ServerOperationError: physicalType: INT64, logicalType: double` on every run.
- **Root cause:** a poll in which no stop had a missing delay made pandas write the delay columns
  as integers; Bronze declares them DOUBLE. One such file in a `COPY INTO` batch made every later
  load fail. (The alerts feed had the same class of bug earlier and was fixed there only.)
- **Fix:** `gtfs_rt_ingest.py` pins `arrival_delay_seconds`, `arrival_time`,
  `departure_delay_seconds` and `departure_time` to float64; a regression test covers it; the five
  affected files were rewritten and re-uploaded; the 24-day backlog then loaded (382,101 rows).

**2. Live trips stopped matching the timetable (from 19 Sep)**
- **Symptom:** the orphan rate (live trips with no matching scheduled trip) went from about 2% to
  about 100% on 19 Sep and stayed there.
- **Root cause:** the static timetable was downloaded once, on 16 Sep, and never refreshed. TfNSW
  rotated its trip IDs, so the old timetable no longer contained the trips running. dbt tests did
  not catch it because orphans are deliberately flagged, not failed.
- **Fix:** the timetable is refreshed daily; Bronze now appends each timetable version instead of
  replacing it (staging takes the newest per key), so history can be reconciled against the
  version that was current at the time; 16-18 Sep were restored this way. 19 Sep to 27 Oct cannot
  be reconciled because those versions were never captured.
- **Side finding:** the non-revenue service `RTTA_REV` was being counted as a passenger line; it is
  now excluded from the passenger marts.

**Why nobody noticed, and what changed**
- `run_pipeline.sh` printed "done" regardless of failures. It now records each step, ends with
  `done OK` or `done FAILED: <steps>`, and exits non-zero (visible as the last exit code in
  `launchctl list`).
- New `ingestion/check_pipeline_health.py` fails the run when Gold has had no new data for 3+
  hours, or when more than 50% of the latest day's trips don't match the timetable.
- Not yet automated: anything that reads the log for you. Check `launchctl list` or
  `grep "^=====" logs/pipeline.log | tail` now and then.
