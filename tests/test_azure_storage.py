import os
from datetime import datetime, timezone

import azure_storage
import pytest

AZURITE = os.environ.get("AZURITE_CONNECTION_STRING")


def test_not_configured_without_environment(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert azure_storage.is_configured() is False


@pytest.mark.parametrize(
    "name,value", [("AZURE_STORAGE_ACCOUNT", "acct"), ("AZURE_STORAGE_CONNECTION_STRING", "UseDev")]
)
def test_configured_by_account_or_connection_string(monkeypatch, name, value):
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv(name, value)
    assert azure_storage.is_configured() is True


def test_container_names_have_defaults_and_can_be_overridden(monkeypatch):
    monkeypatch.delenv("AZURE_RAW_CONTAINER", raising=False)
    assert azure_storage.raw_container() == "raw"
    monkeypatch.setenv("AZURE_RAW_CONTAINER", "custom")
    assert azure_storage.raw_container() == "custom"


needs_azurite = pytest.mark.skipif(
    not AZURITE, reason="set AZURITE_CONNECTION_STRING to run against the Azurite emulator"
)


@needs_azurite
def test_round_trip_against_azurite(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", AZURITE)
    container = "pytest-raw"
    azure_storage.ensure_container(container)

    source = tmp_path / "a.parquet"
    source.write_bytes(b"hello")
    azure_storage.upload_file(source, "feed/x/dt=2026-11-05/a.parquet", container)
    azure_storage.upload_file(source, "other/b.parquet", container)

    blobs = azure_storage.list_blobs("feed/", container)
    assert [b.name for b in blobs] == ["feed/x/dt=2026-11-05/a.parquet"]
    assert blobs[0].size == 5

    destination = tmp_path / "out" / "a.parquet"
    name = "feed/x/dt=2026-11-05/a.parquet"
    downloaded = azure_storage.download_file(name, destination, container)
    assert downloaded.read_bytes() == b"hello"

    newest = azure_storage.latest_modified("feed/", container)
    assert newest is not None and abs((datetime.now(timezone.utc) - newest).total_seconds()) < 120
    assert azure_storage.latest_modified("nothing/", container) is None
