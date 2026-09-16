# Databricks notebook source
# MAGIC %md
# MAGIC # Land GTFS Bronze tables
# MAGIC
# MAGIC Reads whatever `ingestion/gtfs_static_ingest.py` and `ingestion/gtfs_rt_ingest.py`
# MAGIC have deposited in the Unity Catalog volume `workspace.bronze.raw_landing` and
# MAGIC materialises them as Bronze Delta tables. Minimal transformation only — typing
# MAGIC and ingestion metadata, no business logic, no dedup (that's Silver's job).
# MAGIC
# MAGIC Idempotent: static tables are a full overwrite per run (each run reflects the
# MAGIC single, latest static zip present in the volume — TfNSW republishes ~weekly and
# MAGIC we only keep what ingestion landed); RT records are append-only, keyed so a
# MAGIC re-run doesn't duplicate a snapshot already loaded.

# COMMAND ----------

import zipfile
from pathlib import Path

from pyspark.sql import functions as F

CATALOG = "workspace"
VOLUME_ROOT = f"/Volumes/{CATALOG}/bronze/raw_landing"
LOCAL_EXTRACT_DIR = "/local_disk0/tmp/gtfs_static_extract"

spark.sql(f"USE CATALOG {CATALOG}")

# COMMAND ----------

# MAGIC %md ## Static schedule → one Bronze Delta table per GTFS file

# COMMAND ----------

static_dir = Path(f"{VOLUME_ROOT}/gtfs_static/sydneytrains")
zip_paths = sorted(static_dir.glob("*.zip"))
if not zip_paths:
    raise FileNotFoundError(
        f"No static GTFS zip found under {static_dir} — run "
        "ingestion/gtfs_static_ingest.py and upload it to the volume first."
    )
latest_zip = zip_paths[-1]
# filename shape: {captured_at}_{content_hash}.zip — see gtfs_static_ingest.py
feed_version = latest_zip.stem.split("_")[-1]

extract_dir = Path(LOCAL_EXTRACT_DIR)
extract_dir.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(latest_zip) as zf:
    zf.extractall(extract_dir)

STATIC_FILES = {
    "routes.txt": "gtfs_static_routes",
    "stops.txt": "gtfs_static_stops",
    "trips.txt": "gtfs_static_trips",
    "stop_times.txt": "gtfs_static_stop_times",
    "calendar.txt": "gtfs_static_calendar",
}

for filename, table_name in STATIC_FILES.items():
    csv_path = extract_dir / filename
    if not csv_path.exists():
        print(f"skip (not in this feed): {filename}")
        continue

    df = (
        spark.read.option("header", True)
        .option("inferSchema", True)
        .csv(f"file:{csv_path}")
        .withColumn("_feed_version", F.lit(feed_version))
        .withColumn("_source_file", F.lit(latest_zip.name))
        .withColumn("_ingested_at", F.current_timestamp())
    )
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{CATALOG}.bronze.{table_name}")
    )
    print(f"{table_name}: {df.count()} rows (feed_version={feed_version})")

# COMMAND ----------

# MAGIC %md ## Realtime trip updates → append-only Bronze Delta table

# COMMAND ----------

rt_glob = f"{VOLUME_ROOT}/gtfs_rt_trip_updates/sydneytrains/dt=*/*.parquet"
rt_df = spark.read.parquet(rt_glob)

target_table = f"{CATALOG}.bronze.gtfs_rt_trip_updates"
if spark.catalog.tableExists(target_table):
    already_loaded = spark.table(target_table).select("_ingested_at").distinct()
    rt_df = rt_df.join(already_loaded, on="_ingested_at", how="left_anti")

new_row_count = rt_df.count()
if new_row_count == 0:
    print("No new RT snapshots to load — already up to date.")
else:
    (
        rt_df.write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(target_table)
    )
    print(f"Appended {new_row_count} new trip-stop update rows to {target_table}")
