import logging
from datetime import datetime, timedelta, timezone

import jobs
import pytest

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def test_runner_reports_ok(caplog):
    runner = jobs.Runner("t")
    with caplog.at_level(logging.INFO, logger="jobs"):
        assert runner.step("a", lambda: 0) is True
        assert runner.finish() == 0
    assert "done OK" in caplog.text


def test_runner_names_every_failed_step(caplog):
    runner = jobs.Runner("t")
    runner.step("first", lambda: 1)
    runner.step("boom", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    runner.step("fine", lambda: 0)
    with caplog.at_level(logging.INFO, logger="jobs"):
        assert runner.finish() == 1
    assert "done FAILED: first boom" in caplog.text


def test_critical_failure_signals_the_caller_to_stop():
    runner = jobs.Runner("t")
    assert runner.step("critical", lambda: 1, critical=True) is False
    assert runner.step("normal", lambda: 1) is True  # non-critical failures do not stop the chain


def test_static_refresh_asks_the_azure_archive_when_configured(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "acct")
    monkeypatch.setattr(jobs.azure_storage, "latest_modified", lambda prefix, *a: None)
    assert jobs.static_refresh_due(now=NOW) is True  # never downloaded

    recent = NOW - timedelta(hours=3)
    monkeypatch.setattr(jobs.azure_storage, "latest_modified", lambda prefix, *a: recent)
    assert jobs.static_refresh_due(now=NOW) is False

    stale = NOW - timedelta(hours=30)
    monkeypatch.setattr(jobs.azure_storage, "latest_modified", lambda prefix, *a: stale)
    assert jobs.static_refresh_due(now=NOW) is True


def test_static_refresh_uses_local_files_without_azure(monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setattr(jobs, "LOCAL_LANDING_DIR", tmp_path)
    assert jobs.static_refresh_due(now=NOW) is True  # no zip yet

    folder = tmp_path / "gtfs_static" / jobs.AGENCY
    folder.mkdir(parents=True)
    zip_path = folder / "x_abc.zip"
    zip_path.write_bytes(b"z")
    assert jobs.static_refresh_due(now=datetime.now(timezone.utc)) is False


def test_ingest_needs_the_azure_archive(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    with pytest.raises(RuntimeError):
        jobs.ingest()


def test_ingest_runs_both_feeds_even_if_the_first_fails(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "acct")
    import gtfs_alerts_ingest
    import gtfs_rt_ingest

    calls = []
    monkeypatch.setattr(gtfs_rt_ingest, "main", lambda: calls.append("rt") or 1)
    monkeypatch.setattr(gtfs_alerts_ingest, "main", lambda: calls.append("alerts") or 0)

    assert jobs.ingest() == 1
    assert calls == ["rt", "alerts"]


def _patch_transform(monkeypatch, sync_result=0, bronze_result=0):
    import check_pipeline_health
    import export_gold_extracts
    import land_bronze
    import sync_to_volume

    calls = []
    monkeypatch.setattr(jobs, "static_refresh_due", lambda *a, **k: False)
    monkeypatch.setattr(sync_to_volume, "sync", lambda *a, **k: calls.append("sync") or sync_result)
    monkeypatch.setattr(land_bronze, "main", lambda: calls.append("bronze") or bronze_result)
    monkeypatch.setattr(jobs, "_dbt", lambda *a: calls.append("dbt " + a[0]) or 0)
    monkeypatch.setattr(check_pipeline_health, "main", lambda: calls.append("health") or 0)
    monkeypatch.setattr(jobs, "_export_extracts", lambda module: calls.append("export") or 0)
    assert export_gold_extracts is not None
    return calls


def test_transform_runs_every_step_in_order(monkeypatch):
    calls = _patch_transform(monkeypatch)
    assert jobs.transform() == 0
    assert calls == ["sync", "bronze", "dbt build", "dbt source", "health", "export"]


def test_transform_stops_when_databricks_is_unreachable(monkeypatch):
    calls = _patch_transform(monkeypatch, sync_result=1)
    assert jobs.transform() == 1
    assert calls == ["sync"]  # no doomed sessions against a shut-down warehouse


def test_transform_stops_when_bronze_fails(monkeypatch):
    calls = _patch_transform(monkeypatch, bronze_result=1)
    assert jobs.transform() == 1
    assert calls == ["sync", "bronze"]


def test_main_rejects_unknown_commands():
    assert jobs.main(["nonsense"]) == 2
    assert jobs.main([]) == 2
