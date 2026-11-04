import land_bronze
import pytest

TABLES = list(land_bronze.STATIC_FILES.values())


class FakeCursor:
    """Scripted Databricks cursor for the static timetable loader."""

    def __init__(self, in_volume, loaded):
        self.in_volume = in_volume      # versions already unpacked in the volume
        self.loaded = loaded            # {table: set(versions) or None if the table is missing}
        self.statements = []
        self._one = None
        self._all = []
        self.description = [("path",), ("name",), ("size",), ("modification_time",)]

    def execute(self, sql):
        self.statements.append(sql)
        if sql.startswith("LIST"):
            self._all = [("p", f"{v}/", 0, 0) for v in sorted(self.in_volume)]
        elif "information_schema.tables" in sql:
            table = sql.split("table_name = '")[1].split("'")[0]
            self._one = (0 if self.loaded[table] is None else 1,)
        elif sql.startswith("SELECT DISTINCT _feed_version"):
            table = sql.split(".bronze.")[1].strip()
            self._all = [(v,) for v in self.loaded[table]]
        elif sql.startswith("INSERT INTO") or sql.startswith("CREATE TABLE"):
            table = sql.split(".bronze.")[1].split()[0]
            version = sql.split("'")[1]
            self.loaded[table] = (self.loaded[table] or set()) | {version}
        elif sql.startswith("SELECT count(*)"):
            self._one = (5,)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def writes(self):
        return [s for s in self.statements if s.startswith(("INSERT", "CREATE TABLE"))]


@pytest.fixture(autouse=True)
def no_local_zips(monkeypatch):
    monkeypatch.setattr(land_bronze, "all_static_zips", lambda: [])


def test_versions_already_loaded_cause_no_writes():
    cur = FakeCursor({"aaa", "bbb"}, {t: {"aaa", "bbb"} for t in TABLES})
    land_bronze.land_static_bronze(cur)
    assert cur.writes() == []


def test_only_the_missing_table_version_is_loaded_from_the_volume():
    loaded = {t: {"aaa", "bbb"} for t in TABLES}
    loaded["gtfs_static_trips"] = {"aaa"}
    cur = FakeCursor({"aaa", "bbb"}, loaded)

    land_bronze.land_static_bronze(cur)

    writes = cur.writes()
    assert len(writes) == 1
    assert writes[0].startswith("INSERT INTO workspace.bronze.gtfs_static_trips")
    assert "extracted/bbb/trips.txt" in writes[0]
    assert "volume:extracted/bbb" in writes[0]


def test_missing_tables_are_created_for_the_first_version_then_appended():
    cur = FakeCursor({"aaa", "bbb"}, {t: None for t in TABLES})
    land_bronze.land_static_bronze(cur)

    creates = [s for s in cur.writes() if s.startswith("CREATE TABLE")]
    inserts = [s for s in cur.writes() if s.startswith("INSERT INTO")]
    assert len(creates) == len(TABLES) and len(inserts) == len(TABLES)


def test_a_local_only_version_is_unpacked_to_the_volume_first(tmp_path, monkeypatch):
    zip_path = tmp_path / "20261105T000000Z_ccc.zip"
    zip_path.write_bytes(b"zip")
    monkeypatch.setattr(land_bronze, "all_static_zips", lambda: [zip_path])
    uploads = []
    monkeypatch.setattr(land_bronze, "upload_extracted_static_files",
                        lambda zp, version, cur: uploads.append(version))
    cur = FakeCursor({"aaa"}, {t: {"aaa"} for t in TABLES})

    land_bronze.land_static_bronze(cur)

    assert uploads == ["ccc"]  # unpacked once, not once per table
    assert len(cur.writes()) == len(TABLES)


def test_no_version_anywhere_is_a_clear_error():
    cur = FakeCursor(set(), {t: None for t in TABLES})
    with pytest.raises(FileNotFoundError):
        land_bronze.land_static_bronze(cur)


def test_few_statements_per_run_when_everything_is_loaded():
    cur = FakeCursor({"aaa", "bbb", "ccc"}, {t: {"aaa", "bbb", "ccc"} for t in TABLES})
    land_bronze.land_static_bronze(cur)
    # 1 LIST + 2 queries per table, independent of how many versions exist.
    assert len(cur.statements) == 1 + 2 * len(TABLES)
