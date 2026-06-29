"""Tests for the refresh / status / sync endpoints and listing_url enrichment."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.validator import REQUIRED_TOP_LEVEL_KEYS


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient backed by an isolated temp DB (scheduler stays disabled)."""

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    return TestClient(app)


def test_refresh_returns_snapshot_with_sync_metadata(client):
    resp = client.post("/api/refresh")
    assert resp.status_code == 200
    body = resp.json()

    # Strict output keys are all present (inside the refresh envelope).
    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in body
    # Plus the live-ingestion metadata.
    assert "last_synced_at" in body
    assert "jobs" in body and isinstance(body["jobs"], list)
    assert len(body["deals"]) >= 4


def test_refresh_seeds_db_when_empty(client):
    # First call seeds from the bundled sample batch.
    body = client.post("/api/refresh").json()
    assert len(body["deals"]) >= 4


def test_deals_include_listing_url_pointing_at_correct_base(client):
    body = client.post("/api/refresh").json()
    deals = body["deals"]
    assert all("listing_url" in d for d in deals)
    # Every populated listing_url is an absolute http(s) URL.
    for d in deals:
        if d["listing_url"]:
            assert d["listing_url"].startswith(("http://", "https://"))
    # The scaling.com.au sample deals resolve to the scaling base URL.
    scaling = [d for d in deals if d["source_name"] == "scaling.com.au"]
    assert scaling, "expected at least one scaling.com.au deal in sample"
    assert any("scaling.com.au" in (d["listing_url"] or "") for d in scaling)


def test_status_returns_jobs_list(client):
    # Seed first so there is a job row, then check status shape.
    client.post("/api/refresh")
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "last_synced_at" in body
    assert isinstance(body["jobs"], list)


def test_sync_accepts_and_returns_status(client):
    resp = client.post("/api/sync")
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] is True
    assert "jobs" in body


def test_sync_noops_safely_without_credentials(client):
    # Trigger sync synchronously via run_sync to assert no crash + skipped jobs.
    from app.scheduler import run_sync

    result = run_sync()
    assert result["processed"] is False
    assert result["item_count"] == 0
