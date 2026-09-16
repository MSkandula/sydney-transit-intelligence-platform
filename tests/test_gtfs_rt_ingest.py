from datetime import datetime, timezone

import pytest
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from gtfs_rt_ingest import decode_feed, feed_to_records


def _build_sample_feed() -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1_726_000_000  # arbitrary fixed epoch second

    entity = feed.entity.add()
    entity.id = "1"
    trip_update = entity.trip_update
    trip_update.trip.trip_id = "T123.456"
    trip_update.trip.route_id = "T1"
    trip_update.trip.start_date = "20260916"

    stu = trip_update.stop_time_update.add()
    stu.stop_id = "2000123"
    stu.stop_sequence = 5
    stu.arrival.delay = 180
    stu.arrival.time = 1_726_000_100
    stu.departure.delay = 200
    stu.departure.time = 1_726_000_140

    return feed.SerializeToString()


def test_decode_feed_parses_valid_protobuf():
    feed = decode_feed(_build_sample_feed())
    assert len(feed.entity) == 1
    assert feed.entity[0].trip_update.trip.trip_id == "T123.456"


def test_decode_feed_raises_on_garbage_bytes():
    with pytest.raises(DecodeError):
        decode_feed(b"not a protobuf feed")


def test_feed_to_records_flattens_one_row_per_stop_time_update():
    feed = decode_feed(_build_sample_feed())
    ingested_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

    records = feed_to_records(feed, ingested_at)

    assert len(records) == 1
    row = records[0]
    assert row["trip_id"] == "T123.456"
    assert row["route_id"] == "T1"
    assert row["stop_id"] == "2000123"
    assert row["stop_sequence"] == 5
    assert row["arrival_delay_seconds"] == 180
    assert row["departure_delay_seconds"] == 200
    assert row["_ingested_at"] == ingested_at
    assert row["feed_timestamp"] == datetime.fromtimestamp(1_726_000_000, tz=timezone.utc)


def test_feed_to_records_skips_entities_without_trip_update():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add()
    entity.id = "no-trip-update"
    # entity has no trip_update field set at all

    records = feed_to_records(feed, datetime.now(timezone.utc))

    assert records == []


def test_feed_to_records_returns_empty_list_for_empty_feed():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"

    assert feed_to_records(feed, datetime.now(timezone.utc)) == []
