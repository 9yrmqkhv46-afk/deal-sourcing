"""Tests for the additive live-data API layer.

All tests run with NO network. The credential-absent tests assert each endpoint
returns empty results plus a clear ``note`` (no sample fallback). The populated
tests monkeypatch the live module's connector seams to return canned
:class:`SourceItem` objects, so the existing deterministic pipeline shapes real
mapped output without any HTTP call.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import live
from app.live import (
    linkedin_post_from_source_item,
    map_linkedin_record,
    project_deal,
)
from app.main import app
from app.models import LinkedInPost, SourceItem

# Exact contract key sets.
DEAL_KEYS = {
    "id", "source_name", "source_url", "title", "sector", "location",
    "asking_price", "revenue", "ebitda", "listing_date", "thesis_match",
}
THESIS_MATCH_KEYS = {
    "passes_age_filter", "passes_sector_filter", "passes_financial_filter",
    "passes_founder_filter", "ai_automation_potential_flag", "overall_score",
    "classification", "explanation",
}
LINKEDIN_POST_KEYS = {
    "id", "author_name", "author_linkedin_url", "text", "created_at", "url",
}

_CRED_VARS = (
    "APIFY_TOKEN", "APIFY_DEFAULT_ACTOR", "APIFY_ACTOR",
    "LINKEDIN_INGEST_ENABLED", "LINKEDIN_API_TOKEN",
    "FACEBOOK_INGEST_ENABLED", "FACEBOOK_API_TOKEN", "FACEBOOK_GROUP_IDS",
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient on an isolated DB with the scheduler + all creds cleared."""

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "live.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    for var in _CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    return TestClient(app)


# --- Test doubles -----------------------------------------------------------


class FakeConnector:
    """Minimal connector double yielding canned SourceItems with no network."""

    def __init__(self, items=None, configured=True):
        self._items = list(items or [])
        self._configured = configured

    def is_configured(self) -> bool:
        return self._configured

    def fetch(self):
        return list(self._items)


def _broker_item(
    *,
    listing_id: str = "123",
    title: str = "Established Manufacturing Business",
    sector: str = "manufacturing",
) -> SourceItem:
    """A marketplace SourceItem that the pipeline maps into a core_thesis deal."""

    url = f"https://www.bsale.com.au/listing/{listing_id}"
    return SourceItem(
        source_name="Bsale",
        source_type="marketplace",
        raw_text=(
            "Established manufacturing business in Sydney with manual bookkeeping "
            "and clear automation upside."
        ),
        structured={
            "title": title,
            "url": url,
            "company": {
                "name": "Acme Manufacturing",
                "sector": sector,
                "country": "Australia",
                "state": "NSW",
                "city": "Sydney",
                "founded_year": 2005,
            },
            "revenue": 900000,
            "ebitda": 300000,
            "asking_price": 5000000,
            "ai_automation_potential_notes": "Manual back-office with automation upside.",
            "founders": [{"name": "Jane Doe", "role": "Founder", "start_year": 1995}],
            "location_text": "Sydney, NSW",
            "listing_date": "2024-06-01",
        },
        external_listing_id_or_url=url,
    )


def _linkedin_item(post_id: str = "urn:li:1") -> SourceItem:
    url = f"https://www.linkedin.com/posts/{post_id}"
    return SourceItem(
        source_name="LinkedIn",
        source_type="social",
        raw_text="We're selling our Sydney manufacturing business — DM for the deck.",
        structured={
            "id": post_id,
            "author_name": "John Broker",
            "author_linkedin_url": "https://www.linkedin.com/in/johnbroker",
            "text": "Business for sale in Sydney — manufacturing, $5M.",
            "created_at": "2024-06-01T09:00:00Z",
            "url": url,
        },
        external_listing_id_or_url=url,
    )


def _patch_brokers(monkeypatch, items):
    """Route the 'bsale' broker key to a configured fake; others unconfigured."""

    def fake_connector_for(key):
        if key == "bsale":
            return FakeConnector(items=items, configured=True)
        return FakeConnector(items=[], configured=False)

    monkeypatch.setattr(live, "_connector_for", fake_connector_for)


def _patch_linkedin(monkeypatch, items):
    monkeypatch.setattr(live, "_linkedin_connector", lambda: FakeConnector(items=items, configured=True))


# --- Credential-absent behaviour (empty + note, no sample fallback) ---------


def test_brokers_empty_with_note_when_no_source(client):
    body = client.get("/api/brokers/deals").json()
    assert client.get("/api/brokers/deals").status_code == 200
    assert set(body.keys()) == {"deals", "summary", "note"}
    assert body["deals"] == []
    assert body["summary"]["top_core_thesis_deals"] == []
    assert isinstance(body["note"], str) and body["note"].strip()


def test_franchises_empty_with_note_when_no_source(client):
    resp = client.get("/api/franchises/deals")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"deals", "summary", "note"}
    assert body["deals"] == []
    assert body["note"].strip()


def test_insolvency_empty_with_note_when_no_source(client):
    resp = client.get("/api/insolvency/opportunities")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"deals", "summary", "note"}
    assert body["deals"] == []
    assert body["note"].strip()


def test_linkedin_empty_with_note_when_not_configured(client):
    resp = client.get("/api/linkedin/posts")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"linkedin_posts", "summary", "note"}
    assert body["linkedin_posts"] == []
    assert body["summary"]["top_linkedin_posts"] == []
    assert body["note"].strip()


def test_today_empty_with_note_when_nothing_configured(client):
    resp = client.get("/api/live/today")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"deals", "linkedin_posts", "summary", "note"}
    assert body["deals"] == []
    assert body["linkedin_posts"] == []
    assert body["summary"]["top_core_thesis_deals"] == []
    assert body["summary"]["top_linkedin_posts"] == []
    assert body["note"].strip()


# --- Populated brokers via mocked connector ---------------------------------


def test_brokers_returns_mapped_deals_with_thesis_and_summary(client, monkeypatch):
    _patch_brokers(monkeypatch, [_broker_item()])
    body = client.get("/api/brokers/deals?limit=50&country=Australia").json()

    assert body["deals"], "expected at least one mapped live deal"
    deal = body["deals"][0]
    # Deal shape keys match the contract EXACTLY.
    assert set(deal.keys()) == DEAL_KEYS
    assert set(deal["thesis_match"].keys()) == THESIS_MATCH_KEYS

    # Mapped values are real (from the connector item), nothing fabricated.
    assert deal["source_name"] == "Bsale"
    assert deal["sector"] == "manufacturing"
    assert deal["location"] == "Sydney, NSW"
    assert deal["asking_price"] == 5000000
    # source_url is populated from listing_url (base_url + external id).
    assert deal["source_url"] == "https://www.bsale.com.au/listing/123"

    # Strong alignment -> core_thesis and a populated summary.
    assert deal["thesis_match"]["classification"] == "core_thesis"
    summary = body["summary"]
    assert summary["core_thesis_deal_count"] == 1
    assert summary["top_core_thesis_deals"] == [deal["id"]]
    assert body["note"] is None


def test_brokers_respects_limit(client, monkeypatch):
    items = [_broker_item(listing_id=str(i)) for i in range(5)]
    _patch_brokers(monkeypatch, items)
    body = client.get("/api/brokers/deals?limit=2&country=Australia").json()
    assert len(body["deals"]) == 2


# --- LinkedIn mapper + endpoint ---------------------------------------------


def test_map_linkedin_record_is_tolerant():
    records = [
        {
            "id": "p1",
            "authorName": "Jane M&A",
            "authorUrl": "https://www.linkedin.com/in/jane",
            "content": "We just listed a bookkeeping firm for sale.",
            "postedAt": "2024-05-30",
            "postUrl": "https://www.linkedin.com/posts/p1",
        },
        {"text": "no id, only text + url", "url": "https://www.linkedin.com/posts/p2"},
        {"postId": "p3"},  # only an id -> other fields stay None
    ]
    posts = [map_linkedin_record(r) for r in records]
    assert all(isinstance(p, LinkedInPost) for p in posts)

    assert posts[0].id == "p1"
    assert posts[0].author_name == "Jane M&A"
    assert posts[0].author_linkedin_url == "https://www.linkedin.com/in/jane"
    assert posts[0].text == "We just listed a bookkeeping firm for sale."
    assert posts[0].created_at == "2024-05-30"
    assert posts[0].url == "https://www.linkedin.com/posts/p1"

    # No id -> falls back to the url; missing fields stay None (never fabricated).
    assert posts[1].id == "https://www.linkedin.com/posts/p2"
    assert posts[1].author_name is None
    assert posts[2].id == "p3"
    assert posts[2].text is None


def test_linkedin_post_from_source_item_uses_structured_and_fallbacks():
    item = _linkedin_item("urn:li:42")
    post = linkedin_post_from_source_item(item)
    assert post.id == "urn:li:42"
    assert post.author_name == "John Broker"
    assert post.url == "https://www.linkedin.com/posts/urn:li:42"


def test_linkedin_endpoint_returns_posts_when_mocked(client, monkeypatch):
    _patch_linkedin(monkeypatch, [_linkedin_item("a1"), _linkedin_item("a2")])
    body = client.get("/api/linkedin/posts?country=Australia&since_days=1").json()

    assert len(body["linkedin_posts"]) == 2
    post = body["linkedin_posts"][0]
    assert set(post.keys()) == LINKEDIN_POST_KEYS
    assert post["author_name"] == "John Broker"
    assert body["summary"]["top_linkedin_posts"] == ["a1", "a2"]
    assert body["note"] is None


# --- Today aggregator merges + caps -----------------------------------------


def test_today_merges_deals_and_posts(client, monkeypatch):
    _patch_brokers(monkeypatch, [_broker_item(listing_id="1"), _broker_item(listing_id="2")])
    _patch_linkedin(monkeypatch, [_linkedin_item("p1"), _linkedin_item("p2")])
    body = client.get("/api/live/today").json()

    assert set(body.keys()) == {"deals", "linkedin_posts", "summary", "note"}
    assert len(body["deals"]) == 2
    assert len(body["linkedin_posts"]) == 2
    assert "top_core_thesis_deals" in body["summary"]
    assert "top_linkedin_posts" in body["summary"]


def test_today_caps_top_lists(client, monkeypatch):
    deals = [_broker_item(listing_id=str(i)) for i in range(25)]
    posts = [_linkedin_item(f"p{i}") for i in range(55)]
    _patch_brokers(monkeypatch, deals)
    _patch_linkedin(monkeypatch, posts)
    body = client.get("/api/live/today").json()

    assert len(body["deals"]) == 25
    assert len(body["linkedin_posts"]) == 55
    # Top lists are capped at 20 (deals) and 50 (posts).
    assert len(body["summary"]["top_core_thesis_deals"]) == 20
    assert len(body["summary"]["top_linkedin_posts"]) == 50


# --- Pure projection helper -------------------------------------------------


def test_project_deal_shape_exact(client, monkeypatch):
    """project_deal yields exactly the contract keys for a processed deal."""

    from app.pipeline import process_batch

    output = process_batch([_broker_item()])
    companies_by_id = {c.company_id: c for c in output.companies}
    projected = project_deal(output.deals[0], companies_by_id)
    assert set(projected.keys()) == DEAL_KEYS
    assert projected["source_url"] == "https://www.bsale.com.au/listing/123"
