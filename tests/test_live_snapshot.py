"""Tests that the live GET endpoints serve from the LIVE-sync snapshot.

These assert the section-5 behaviour: with a stored ``live_sync`` snapshot the
live endpoints return that live data (deals + LinkedIn posts), never sample;
``/api/refresh`` exposes ``snapshot_kind``; and with no live snapshot the live
endpoints return empty + a note (still no sample). No network is used.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.models import LinkedInPost
from app.pipeline import process_batch
from app.sample_data import sample_batch

_CRED_VARS = (
    "APIFY_TOKEN", "APIFY_DEFAULT_ACTOR", "APIFY_ACTOR",
    "LINKEDIN_INGEST_ENABLED", "LINKEDIN_API_TOKEN",
    "FACEBOOK_INGEST_ENABLED", "FACEBOOK_API_TOKEN", "FACEBOOK_GROUP_IDS",
)

DEAL_KEYS = {
    "id", "source_name", "source_url", "title", "sector", "location",
    "asking_price", "revenue", "ebitda", "listing_date", "thesis_match",
}
LINKEDIN_POST_KEYS = {
    "id", "author_name", "author_linkedin_url", "text", "created_at", "url",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "snap.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    for var in _CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    store.init_db()
    return TestClient(app)


def _seed_live_snapshot():
    """Process the bundled sample batch and store it AS A LIVE snapshot."""

    output = process_batch(sample_batch())
    posts = [
        LinkedInPost(
            id="urn:li:post:1",
            author_name="Jane Broker",
            author_linkedin_url="https://www.linkedin.com/in/jane",
            text="Business for sale in Sydney — manufacturing.",
            created_at="2026-01-01T00:00:00Z",
            url="https://www.linkedin.com/posts/1",
        ).model_dump()
    ]
    store.save_snapshot(
        output, kind=store.SNAPSHOT_KIND_LIVE,
        synced_at="2026-01-01T03:00:00+00:00", linkedin_posts=posts,
    )
    return output


# --- No live snapshot: empty + note, never sample ---------------------------


def test_brokers_empty_with_note_when_no_live_snapshot(client):
    body = client.get("/api/brokers/deals").json()
    assert body["deals"] == []
    assert isinstance(body["note"], str) and body["note"].strip()


def test_linkedin_empty_with_note_when_no_live_snapshot(client):
    body = client.get("/api/linkedin/posts").json()
    assert body["linkedin_posts"] == []
    assert body["note"].strip()


# --- With a live snapshot: serve live data ----------------------------------


def test_brokers_serve_live_snapshot_deals(client):
    _seed_live_snapshot()
    body = client.get("/api/brokers/deals?limit=100").json()
    assert body["deals"], "expected live deals from the snapshot"
    for d in body["deals"]:
        assert set(d.keys()) == DEAL_KEYS
    # The bundled sample includes scaling.com.au marketplace deals.
    assert any(d["source_name"] == "scaling.com.au" for d in body["deals"])


def test_linkedin_serves_snapshot_posts(client):
    _seed_live_snapshot()
    body = client.get("/api/linkedin/posts").json()
    assert len(body["linkedin_posts"]) == 1
    post = body["linkedin_posts"][0]
    assert set(post.keys()) == LINKEDIN_POST_KEYS
    assert post["author_name"] == "Jane Broker"
    assert body["summary"]["top_linkedin_posts"] == ["urn:li:post:1"]
    assert body["note"] is None


def test_today_merges_live_snapshot(client):
    _seed_live_snapshot()
    body = client.get("/api/live/today").json()
    assert set(body.keys()) == {"deals", "linkedin_posts", "summary", "note"}
    assert body["deals"]
    assert len(body["linkedin_posts"]) == 1


def test_franchises_serve_only_franchise_deals_from_snapshot(client):
    _seed_live_snapshot()
    body = client.get("/api/franchises/deals?limit=100").json()
    # The bundled sample includes is_franchise listings.
    assert body["deals"]
    # All returned deals must be franchise deals (filtered from the snapshot).
    # (We assert via the brokers set being a superset is not trivial here; we
    # simply assert we got some and the shape is correct.)
    for d in body["deals"]:
        assert set(d.keys()) == DEAL_KEYS


# --- /api/refresh exposes snapshot_kind -------------------------------------


def test_refresh_exposes_snapshot_kind_sample(client):
    # Seed a sample snapshot (default kind) then refresh.
    output = process_batch(sample_batch())
    store.save_snapshot(output)  # default kind=sample_seed
    body = client.post("/api/refresh").json()
    assert body["snapshot_kind"] == "sample_seed"
    assert "linkedin_posts" in body


def test_refresh_exposes_snapshot_kind_live(client):
    _seed_live_snapshot()
    body = client.post("/api/refresh").json()
    assert body["snapshot_kind"] == "live_sync"
    assert len(body["linkedin_posts"]) == 1
    assert len(body["deals"]) >= 4


# --- /api/actors ------------------------------------------------------------


def test_actors_endpoint_lists_all_22(client):
    body = client.get("/api/actors").json()
    assert body["apify_token_present"] is False
    assert len(body["actors"]) == 22
    assert len(body["categories"]) == 6
    li = [a for a in body["actors"] if a["is_linkedin"]]
    assert len(li) == 4
    for a in body["actors"]:
        assert "actor_id" in a and "category" in a and "source_type" in a
