from datetime import date

import pytest
import sync_to_volume as sync_mod


class FakeCursor:
    """Records PUT statements; LIST returns whatever the test says is already in the volume."""

    def __init__(self, in_volume):
        self.in_volume = in_volume  # {directory: {file names}}
        self.puts = []
        self._rows = []
        self.description = [("path",), ("name",), ("size",), ("modification_time",)]

    def execute(self, sql):
        if sql.startswith("LIST"):
            directory = sql.split("raw_landing/")[1].rstrip("/'")
            if directory not in self.in_volume:
                raise RuntimeError("path does not exist")
            self._rows = [("p", name, 1, 0) for name in self.in_volume[directory]]
        elif sql.startswith("PUT"):
            self.puts.append(sql)

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def _make_files(root, feed, day, names):
    folder = root / feed / "sydneytrains" / f"dt={day}"
    folder.mkdir(parents=True)
    for n in names:
        (folder / n).write_bytes(b"x")


@pytest.fixture
def landing(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mod, "LOCAL_LANDING_DIR", tmp_path)
    return tmp_path


def test_uploads_only_files_missing_from_the_volume(landing, monkeypatch):
    files = ["a.parquet", "b.parquet", "c.parquet"]
    _make_files(landing, "gtfs_rt_trip_updates", "2026-11-04", files)
    cursor = FakeCursor({"gtfs_rt_trip_updates/sydneytrains/dt=2026-11-04": {"a.parquet"}})
    monkeypatch.setattr(sync_mod, "connect", lambda: FakeConn(cursor))

    failed = sync_mod.sync("local", days=7, today=date(2026, 11, 5))

    assert failed == 0
    assert sorted(p.split("raw_landing/")[1].split("'")[0] for p in cursor.puts) == [
        "gtfs_rt_trip_updates/sydneytrains/dt=2026-11-04/b.parquet",
        "gtfs_rt_trip_updates/sydneytrains/dt=2026-11-04/c.parquet",
    ]


def test_a_missing_volume_directory_means_everything_is_uploaded(landing, monkeypatch):
    _make_files(landing, "gtfs_service_alerts", "2026-11-05", ["x.parquet", "y.parquet"])
    cursor = FakeCursor({})
    monkeypatch.setattr(sync_mod, "connect", lambda: FakeConn(cursor))

    assert sync_mod.sync("local", days=7, today=date(2026, 11, 5)) == 0
    assert len(cursor.puts) == 2


def test_files_older_than_the_window_are_ignored(landing, monkeypatch):
    _make_files(landing, "gtfs_rt_trip_updates", "2026-10-01", ["old.parquet"])
    _make_files(landing, "gtfs_rt_trip_updates", "2026-11-04", ["new.parquet"])
    cursor = FakeCursor({})
    monkeypatch.setattr(sync_mod, "connect", lambda: FakeConn(cursor))

    sync_mod.sync("local", days=3, today=date(2026, 11, 5))
    assert len(cursor.puts) == 1 and "new.parquet" in cursor.puts[0]


def test_dry_run_uploads_nothing(landing, monkeypatch):
    _make_files(landing, "gtfs_rt_trip_updates", "2026-11-05", ["a.parquet"])
    cursor = FakeCursor({})
    monkeypatch.setattr(sync_mod, "connect", lambda: FakeConn(cursor))

    assert sync_mod.sync("local", days=7, dry_run=True, today=date(2026, 11, 5)) == 0
    assert cursor.puts == []


def test_nothing_to_sync_does_not_open_a_databricks_session(landing, monkeypatch):
    def boom():
        raise AssertionError("must not connect when there is nothing to do")

    monkeypatch.setattr(sync_mod, "connect", boom)
    assert sync_mod.sync("local", days=7, today=date(2026, 11, 5)) == 0


def test_failed_uploads_are_counted_and_the_rest_continue(landing, monkeypatch):
    _make_files(landing, "gtfs_rt_trip_updates", "2026-11-05", ["a.parquet", "b.parquet"])
    cursor = FakeCursor({})
    original = cursor.execute

    def flaky(sql):
        if "a.parquet" in sql:
            raise RuntimeError("boom")
        original(sql)

    cursor.execute = flaky
    monkeypatch.setattr(sync_mod, "connect", lambda: FakeConn(cursor))

    assert sync_mod.sync("local", days=7, today=date(2026, 11, 5)) == 1
    assert len(cursor.puts) == 1 and "b.parquet" in cursor.puts[0]
