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
