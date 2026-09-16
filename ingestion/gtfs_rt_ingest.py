"""Poll the TfNSW GTFS-Realtime v2 Trip Updates feed for Sydney Trains, decode the
protobuf FeedMessage, flatten it to one row per (trip, stop) update, and land it
locally as a timestamped Parquet snapshot.

Phase 1: lands to data/bronze/gtfs_rt_trip_updates/ (local, git-ignored). Phase 2
replaces the local landing step with a scheduled Databricks Job appending directly
to a Bronze Delta table — the fetch/decode/flatten logic here doesn't change.
"""

import logging
import sys
from datetime import datetime, timezone

import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2

from config import AGENCY, GTFS_REALTIME_V2_BASE_URL, LOCAL_LANDING_DIR, auth_headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


def fetch_trip_updates(agency: str = AGENCY) -> bytes:
    url = f"{GTFS_REALTIME_V2_BASE_URL}/{agency}"
    response = requests.get(url, headers=auth_headers(), timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    content = response.content
    if not content:
        raise ValueError(f"Empty response body from {url}")
    return content


def decode_feed(content: bytes) -> gtfs_realtime_pb2.FeedMessage:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)  # raises google.protobuf.message.DecodeError on garbage input
    return feed


def feed_to_records(feed: gtfs_realtime_pb2.FeedMessage, ingested_at: datetime) -> list[dict]:
    """One row per stop_time_update per trip entity — the natural grain for the
    Silver reconciliation step (join to static schedule on trip_id + stop_sequence)."""
    feed_timestamp = (
        datetime.fromtimestamp(feed.header.timestamp, tz=timezone.utc)
        if feed.header.timestamp
        else None
    )

    records = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update
        trip = trip_update.trip

        for stu in trip_update.stop_time_update:
            records.append(
                {
                    "entity_id": entity.id,
                    "trip_id": trip.trip_id,
                    "route_id": trip.route_id,
                    "start_date": trip.start_date,
                    "schedule_relationship": trip.ScheduleRelationship.Name(
                        trip.schedule_relationship
                    ),
                    "stop_id": stu.stop_id,
                    "stop_sequence": stu.stop_sequence,
                    "arrival_delay_seconds": (
                        stu.arrival.delay if stu.HasField("arrival") else None
                    ),
                    "arrival_time": (
                        stu.arrival.time if stu.HasField("arrival") else None
                    ),
                    "departure_delay_seconds": (
                        stu.departure.delay if stu.HasField("departure") else None
                    ),
                    "departure_time": (
                        stu.departure.time if stu.HasField("departure") else None
                    ),
                    "stop_schedule_relationship": stu.ScheduleRelationship.Name(
                        stu.schedule_relationship
                    ),
                    "feed_timestamp": feed_timestamp,
                    "_ingested_at": ingested_at,
                }
            )
    return records


def save_snapshot(records: list[dict], ingested_at: datetime, agency: str = AGENCY):
    if not records:
        log.warning("No trip_update records in this poll — feed may be between updates.")

    date_partition = ingested_at.strftime("%Y-%m-%d")
    ts_tag = ingested_at.strftime("%Y%m%dT%H%M%SZ")
    out_dir = LOCAL_LANDING_DIR / "gtfs_rt_trip_updates" / agency / f"dt={date_partition}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{ts_tag}.parquet"

    df = pd.DataFrame(records)
    df.to_parquet(out_path, index=False)
    return out_path


def main() -> int:
    ingested_at = datetime.now(timezone.utc)
    try:
        content = fetch_trip_updates()
        feed = decode_feed(content)
    except requests.RequestException:
        log.exception("Failed to fetch GTFS-RT trip updates for %s", AGENCY)
        return 1
    except Exception:
        log.exception("Failed to decode GTFS-RT protobuf response for %s", AGENCY)
        return 1

    records = feed_to_records(feed, ingested_at)
    out_path = save_snapshot(records, ingested_at)
    log.info(
        "Saved %d trip-stop update records to %s", len(records), out_path
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
