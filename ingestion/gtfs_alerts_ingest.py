"""Poll the TfNSW GTFS-Realtime v2 Service Alerts feed for Sydney Trains, decode the
protobuf FeedMessage, flatten it to one row per (alert, informed entity), and land it.

Mirrors gtfs_rt_ingest.py's pattern exactly (same feed message type, same landing
convention) — see that file's docstring for the general design. This feed unlocks
the "do disruption alerts actually correlate with measurable delay spikes" business
question from PROJECT_PLAN.md §3, which trip updates alone can't answer.

Flattening note: an alert can have multiple active_period entries (e.g. recurring
maintenance windows); this takes only the first one per alert. Good enough for the
MVP business question (does *an* alert overlap with a delay spike), and simpler to
reason about than a second explode — documented here rather than silently assumed.
"""

import logging
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import requests
from config import AGENCY, LOCAL_LANDING_DIR, auth_headers
from databricks_upload import upload_to_volume
from google.transit import gtfs_realtime_pb2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
ALERTS_V2_BASE_URL = "https://api.transport.nsw.gov.au/v2/gtfs/alerts"


def fetch_alerts(agency: str = AGENCY) -> bytes:
    url = f"{ALERTS_V2_BASE_URL}/{agency}"
    response = requests.get(url, headers=auth_headers(), timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    content = response.content
    if not content:
        raise ValueError(f"Empty response body from {url}")
    return content


def decode_feed(content: bytes) -> gtfs_realtime_pb2.FeedMessage:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)
    return feed


def feed_to_records(feed: gtfs_realtime_pb2.FeedMessage, ingested_at: datetime) -> list[dict]:
    records = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert

        active_start, active_end = None, None
        if alert.active_period:
            period = alert.active_period[0]
            active_start = (
                datetime.fromtimestamp(period.start, tz=timezone.utc)
                if period.start
                else None
            )
            active_end = (
                datetime.fromtimestamp(period.end, tz=timezone.utc)
                if period.end
                else None
            )

        header = alert.header_text.translation[0].text if alert.header_text.translation else None
        description = (
            alert.description_text.translation[0].text
            if alert.description_text.translation
            else None
        )

        informed_entities = alert.informed_entity or [None]
        for ie in informed_entities:
            records.append(
                {
                    "entity_id": entity.id,
                    "cause": alert.Cause.Name(alert.cause),
                    "effect": alert.Effect.Name(alert.effect),
                    "header_text": header,
                    "description_text": description,
                    "route_id": ie.route_id if ie else None,
                    "stop_id": ie.stop_id if ie else None,
                    "trip_id": ie.trip.trip_id if ie and ie.HasField("trip") else None,
                    "active_period_start": active_start,
                    "active_period_end": active_end,
                    "_ingested_at": ingested_at,
                }
            )
    return records


# Columns that can legitimately be all-null in a given poll (e.g. no trip-level
# alerts this time) — pandas infers an all-None column's dtype as generic `object`,
# which pyarrow can write as a null-typed parquet column instead of string, causing
# a Delta schema conflict on COPY INTO the moment a later poll *does* have a value.
# Caught via a real ServerOperationError (DELTA_FAILED_TO_MERGE_FIELDS on trip_id),
# not anticipated in advance — explicit casting forces a consistent string schema.
NULLABLE_STRING_COLUMNS = ["route_id", "stop_id", "trip_id", "description_text"]


def save_snapshot(records: list[dict], ingested_at: datetime, agency: str = AGENCY):
    date_partition = ingested_at.strftime("%Y-%m-%d")
    ts_tag = ingested_at.strftime("%Y%m%dT%H%M%SZ")
    out_dir = LOCAL_LANDING_DIR / "gtfs_service_alerts" / agency / f"dt={date_partition}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{ts_tag}.parquet"

    df = pd.DataFrame(records)
    for col in NULLABLE_STRING_COLUMNS:
        df[col] = df[col].astype("string")
    df.to_parquet(out_path, index=False)
    return out_path


def main() -> int:
    ingested_at = datetime.now(timezone.utc)
    try:
        content = fetch_alerts()
        feed = decode_feed(content)
    except requests.RequestException:
        log.exception("Failed to fetch GTFS-RT service alerts for %s", AGENCY)
        return 1
    except Exception:
        log.exception("Failed to decode GTFS-RT alerts protobuf response for %s", AGENCY)
        return 1

    records = feed_to_records(feed, ingested_at)
    if not records:
        log.info("No active alerts this poll — nothing to save.")
        return 0

    out_path = save_snapshot(records, ingested_at)
    log.info("Saved %d alert-entity records to %s", len(records), out_path)

    if os.environ.get("DATABRICKS_HOST"):
        date_partition = ingested_at.strftime("%Y-%m-%d")
        volume_subpath = f"gtfs_service_alerts/{AGENCY}/dt={date_partition}/{out_path.name}"
        try:
            upload_to_volume(out_path, volume_subpath)
        except Exception:
            log.exception("Landed locally but failed to upload to Databricks volume")
            return 1
    else:
        log.info("DATABRICKS_HOST not set — skipping volume upload (local-only run)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
