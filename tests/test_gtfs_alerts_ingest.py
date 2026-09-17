from datetime import datetime, timezone

from google.transit import gtfs_realtime_pb2

from gtfs_alerts_ingest import decode_feed, feed_to_records


def _build_sample_feed() -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1_726_000_000

    entity = feed.entity.add()
    entity.id = "alert-1"
    alert = entity.alert
    alert.cause = gtfs_realtime_pb2.Alert.MAINTENANCE
    alert.effect = gtfs_realtime_pb2.Alert.MODIFIED_SERVICE
    alert.header_text.translation.add(text="Buses replace trains", language="en")
    alert.description_text.translation.add(text="Between A and B", language="en")

    period = alert.active_period.add()
    period.start = 1_726_000_000
    period.end = 1_726_010_000

    ie1 = alert.informed_entity.add()
    ie1.route_id = "T1"
    ie2 = alert.informed_entity.add()
    ie2.route_id = "T2"

    return feed.SerializeToString()


def test_decode_feed_parses_valid_protobuf():
    feed = decode_feed(_build_sample_feed())
    assert len(feed.entity) == 1
    assert feed.entity[0].alert.header_text.translation[0].text == "Buses replace trains"


def test_feed_to_records_flattens_one_row_per_informed_entity():
    feed = decode_feed(_build_sample_feed())
    ingested_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

    records = feed_to_records(feed, ingested_at)

    assert len(records) == 2
    assert {r["route_id"] for r in records} == {"T1", "T2"}
    for r in records:
        assert r["cause"] == "MAINTENANCE"
        assert r["effect"] == "MODIFIED_SERVICE"
        assert r["header_text"] == "Buses replace trains"
        assert r["description_text"] == "Between A and B"
        assert r["active_period_start"] == datetime.fromtimestamp(
            1_726_000_000, tz=timezone.utc
        )
        assert r["active_period_end"] == datetime.fromtimestamp(
            1_726_010_000, tz=timezone.utc
        )
        assert r["_ingested_at"] == ingested_at


def test_feed_to_records_skips_entities_without_alert():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add()
    entity.id = "no-alert"

    records = feed_to_records(feed, datetime.now(timezone.utc))

    assert records == []


def test_feed_to_records_handles_alert_with_no_active_period():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add()
    entity.id = "open-ended"
    alert = entity.alert
    alert.header_text.translation.add(text="Station update", language="en")
    ie = alert.informed_entity.add()
    ie.route_id = "T5"

    records = feed_to_records(feed, datetime.now(timezone.utc))

    assert len(records) == 1
    assert records[0]["active_period_start"] is None
    assert records[0]["active_period_end"] is None
    assert records[0]["cause"] == "UNKNOWN_CAUSE"
    assert records[0]["effect"] == "UNKNOWN_EFFECT"
