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



# --- /api/sync never 500s ----------------------------------------------------


def test_sync_includes_message_and_never_500(client):
    resp = client.post("/api/sync")
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] is True
    assert isinstance(body["message"], str) and body["message"]


def test_sync_returns_202_even_when_scheduling_fails(client, monkeypatch):
    """If queuing the background task raises, /api/sync still returns a clean 202."""

    import app.main as main

    def _boom(*a, **k):
        raise RuntimeError("queue down")

    # Force the background scheduling to raise; the endpoint must not 500.
    monkeypatch.setattr(main.BackgroundTasks, "add_task", _boom)
    resp = client.post("/api/sync")
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] is False
    assert "could not start sync" in body["message"]


# --- /api/diagnostics --------------------------------------------------------


def test_diagnostics_no_token_no_network(client, monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)

    # Guard: no network call must happen when there is no token.
    import requests

    def _no_net(*a, **k):
        raise AssertionError("network must not be called without a token")

    monkeypatch.setattr(requests, "get", _no_net)

    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_present"] is False
    assert body["token_length"] == 0
    assert body["token_valid"] is None
    assert body["apify_user"] is None
    assert body["actor_count"] == 30
    assert isinstance(body["sync_times"], list)
    assert body["message"]


def test_diagnostics_valid_token(client, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "good-token")

    class _Resp:
        status_code = 200

        def json(self):
            return {"data": {"username": "transformbiz", "id": "u123"}}

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    body = client.get("/api/diagnostics").json()
    assert body["token_present"] is True
    assert body["token_length"] == len("good-token")
    assert body["token_valid"] is True
    assert body["apify_user"] == "transformbiz"
    assert body["http_status"] == 200


def test_diagnostics_invalid_token_401(client, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "bad-token")

    class _Resp:
        status_code = 401

        def json(self):
            return {"error": {"message": "invalid token"}}

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    body = client.get("/api/diagnostics").json()
    assert body["token_present"] is True
    assert body["token_valid"] is False
    assert body["http_status"] == 401
    assert body["apify_user"] is None
    assert "401" in body["message"]


def test_diagnostics_network_error_never_500(client, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "some-token")

    import requests

    def _boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(requests, "get", _boom)
    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_valid"] is False
    assert "Could not reach Apify" in body["message"]
