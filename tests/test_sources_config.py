"""Tests for per-source config diagnostics, /api/sources, and sync messages.

These cover the live-source transparency layer: the deterministic
``actor_env_var`` naming, ``source_config_status`` reporting configured vs
needs-key, the ``GET /api/sources`` endpoint shape, and the "skipped: no API
key" sync messages when sources are unconfigured. No network access occurs.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sources import (
    REGISTRY,
    actor_env_var,
    apify_token_present,
    source_config_status,
)


# Env vars that, when present, would make a source look "configured".
_CRED_VARS = (
    "APIFY_TOKEN",
    "LINKEDIN_INGEST_ENABLED",
    "LINKEDIN_API_TOKEN",
    "FACEBOOK_INGEST_ENABLED",
    "FACEBOOK_API_TOKEN",
    "FACEBOOK_GROUP_IDS",
)


def _clear_creds(monkeypatch):
    for var in _CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    # Also clear every per-source actor id so the default state is "needs key".
    for entry in REGISTRY.all():
        monkeypatch.delenv(actor_env_var(entry.key), raising=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sources.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    _clear_creds(monkeypatch)
    return TestClient(app)


# --- actor_env_var canonical names ------------------------------------------

@pytest.mark.parametrize(
    "source_key,expected",
    [
        ("scaling.com.au", "APIFY_ACTOR_SCALING_COM_AU"),
        ("scalingup.com.au", "APIFY_ACTOR_SCALINGUP_COM_AU"),
        ("businessforsale", "APIFY_ACTOR_BUSINESSFORSALE"),
        ("bsale", "APIFY_ACTOR_BSALE"),
        ("anybusiness", "APIFY_ACTOR_ANYBUSINESS"),
        ("allbusiness", "APIFY_ACTOR_ALLBUSINESS"),
        ("linkbusiness", "APIFY_ACTOR_LINKBUSINESS"),
        ("sbx", "APIFY_ACTOR_SBX"),
        ("resolve", "APIFY_ACTOR_RESOLVE"),
        ("benchmark", "APIFY_ACTOR_BENCHMARK"),
        ("businessesforsale_au", "APIFY_ACTOR_BUSINESSESFORSALE_AU"),
        ("franchise2sell", "APIFY_ACTOR_FRANCHISE2SELL"),
    ],
)
def test_actor_env_var_canonical_names(source_key, expected):
    assert actor_env_var(source_key) == expected


def test_actor_env_var_is_deterministic_and_prefixed():
    for entry in REGISTRY.all():
        name = actor_env_var(entry.key)
        assert name.startswith("APIFY_ACTOR_")
        assert name == name.upper()
        assert "." not in name and "-" not in name


# --- source_config_status configured flag -----------------------------------

def test_status_reports_not_configured_without_env(monkeypatch):
    _clear_creds(monkeypatch)
    statuses = source_config_status()
    assert apify_token_present() is False
    assert len(statuses) == len(REGISTRY.all())
    for s in statuses:
        assert s["configured"] is False
        # Every status carries the documented fields.
        for field in ("key", "name", "source_type", "base_url", "configured",
                      "actor_env_var", "requires", "note"):
            assert field in s
        assert s["actor_env_var"] == actor_env_var(s["key"])


def test_status_reports_configured_with_token_and_actor(monkeypatch):
    _clear_creds(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN", "secret-token")
    monkeypatch.setenv("APIFY_ACTOR_BSALE", "acme/bsale-actor")

    statuses = {s["key"]: s for s in source_config_status()}
    assert apify_token_present() is True
    # The source whose actor id is set is now configured ...
    assert statuses["bsale"]["configured"] is True
    # ... while another apify source without its actor id is not.
    assert statuses["resolve"]["configured"] is False


def test_status_requires_field_distinguishes_social(monkeypatch):
    _clear_creds(monkeypatch)
    statuses = {s["key"]: s for s in source_config_status()}
    assert statuses["linkedin"]["requires"] == "linkedin"
    assert statuses["facebook_groups"]["requires"] == "facebook"
    assert statuses["bsale"]["requires"] == "apify"


def test_status_includes_twelve_apify_sources(monkeypatch):
    _clear_creds(monkeypatch)
    apify = [s for s in source_config_status() if s["requires"] == "apify"]
    assert len(apify) == 12


# --- GET /api/sources --------------------------------------------------------

def test_api_sources_lists_all_sources_with_fields(client):
    resp = client.get("/api/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["apify_token_present"] is False
    sources = body["sources"]
    assert len(sources) == len(REGISTRY.all())
    keys = {s["key"] for s in sources}
    # All registered keys are present, including the new scalingup sibling.
    assert REGISTRY.get("scalingup.com.au") is not None
    assert "scalingup.com.au" in keys
    for s in sources:
        assert s["configured"] is False
        assert s["actor_env_var"].startswith("APIFY_ACTOR_")


def test_api_sources_reflects_configuration(client, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "secret")
    monkeypatch.setenv("APIFY_ACTOR_RESOLVE", "acme/resolve")
    body = client.get("/api/sources").json()
    assert body["apify_token_present"] is True
    resolve = [s for s in body["sources"] if s["key"] == "resolve"][0]
    assert resolve["configured"] is True


# --- /api/sync yields "skipped: no API key" when unconfigured ----------------

def test_sync_marks_unconfigured_sources_skipped(client, monkeypatch):
    _clear_creds(monkeypatch)
    from app.scheduler import run_sync

    result = run_sync()
    assert result["processed"] is False
    assert result["item_count"] == 0

    jobs = client.get("/api/status").json()["jobs"]
    assert jobs, "expected per-source job rows after a sync"
    skipped = [j for j in jobs if j["status"] == "skipped"]
    assert skipped, "expected skipped jobs when no credentials are present"
    assert all(j["message"] == "skipped: no API key" for j in skipped)
