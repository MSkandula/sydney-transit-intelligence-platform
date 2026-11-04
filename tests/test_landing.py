from pathlib import Path

import landing


def _clear(monkeypatch):
    for name in ("AZURE_STORAGE_ACCOUNT", "AZURE_STORAGE_CONNECTION_STRING", "ARCHIVE_TO_AZURE",
                 "UPLOAD_TO_DATABRICKS", "DATABRICKS_HOST"):
        monkeypatch.delenv(name, raising=False)


def test_default_behaviour_is_unchanged_without_azure(monkeypatch):
    _clear(monkeypatch)
    assert landing.archive_enabled() is False
    assert landing.databricks_upload_enabled() is False  # no DATABRICKS_HOST: local-only run
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    assert landing.databricks_upload_enabled() is True  # the laptop pipeline's behaviour


def test_explicit_flag_overrides_the_default(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    monkeypatch.setenv("UPLOAD_TO_DATABRICKS", "false")
    assert landing.databricks_upload_enabled() is False
    monkeypatch.setenv("UPLOAD_TO_DATABRICKS", "TRUE")
    assert landing.databricks_upload_enabled() is True


def test_archive_can_be_switched_off(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "acct")
    assert landing.archive_enabled() is True
    monkeypatch.setenv("ARCHIVE_TO_AZURE", "false")
    assert landing.archive_enabled() is False


def test_land_file_archives_then_uploads(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "acct")
    monkeypatch.setenv("UPLOAD_TO_DATABRICKS", "true")
    calls = []
    monkeypatch.setattr(
        landing.azure_storage, "upload_file", lambda p, b, *a: calls.append(("azure", b))
    )
    import databricks_upload
    monkeypatch.setattr(
        databricks_upload, "upload_to_volume", lambda p, s: calls.append(("volume", s))
    )

    landing.land_file(Path("x.parquet"), "feed/a/x.parquet")
    assert calls == [("azure", "feed/a/x.parquet"), ("volume", "feed/a/x.parquet")]


def test_ingest_mode_archives_only(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "acct")
    monkeypatch.setenv("UPLOAD_TO_DATABRICKS", "false")
    calls = []
    monkeypatch.setattr(landing.azure_storage, "upload_file", lambda p, b, *a: calls.append(b))
    import databricks_upload
    monkeypatch.setattr(databricks_upload, "upload_to_volume", lambda p, s: calls.append("VOLUME"))

    landing.land_file(Path("x.parquet"), "feed/a/x.parquet")
    assert calls == ["feed/a/x.parquet"]
