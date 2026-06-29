"""Tests for the credential-gated connectors.

These tests run with NO network and NO credentials, asserting connectors no-op
safely. The Apify mapping test feeds a mocked dataset payload (no HTTP call).
"""

import pytest

from app.connectors import (
    ApifyConnector,
    FacebookGroupsConnector,
    LinkedInConnector,
    get_connector,
)
from app.models import SourceItem, SourceType


# --- credential-absent no-op behaviour --------------------------------------

def _clear_creds(monkeypatch):
    for var in (
        "APIFY_TOKEN",
        "APIFY_DEFAULT_ACTOR",
        "APIFY_ACTOR",
        "LINKEDIN_INGEST_ENABLED",
        "LINKEDIN_API_TOKEN",
        "FACEBOOK_INGEST_ENABLED",
        "FACEBOOK_API_TOKEN",
        "FACEBOOK_GROUP_IDS",
    ):
        monkeypatch.delenv(var, raising=False)


def test_apify_connector_noops_without_token(monkeypatch):
    _clear_creds(monkeypatch)
    conn = ApifyConnector("bsale")
    assert conn.is_configured() is False
    assert conn.fetch() == []


def test_apify_connector_noops_without_actor_even_with_token(monkeypatch):
    _clear_creds(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN", "secret")
    # No APIFY_ACTOR_BSALE configured -> still not configured.
    monkeypatch.delenv("APIFY_ACTOR_BSALE", raising=False)
    conn = ApifyConnector("bsale")
    assert conn.is_configured() is False
    assert conn.fetch() == []


def test_linkedin_connector_noops_when_disabled(monkeypatch):
    _clear_creds(monkeypatch)
    conn = LinkedInConnector()
    assert conn.is_configured() is False
    assert conn.fetch() == []


def test_facebook_connector_noops_when_disabled(monkeypatch):
    _clear_creds(monkeypatch)
    conn = FacebookGroupsConnector()
    assert conn.is_configured() is False
    assert conn.fetch() == []


def test_facebook_connector_requires_group_ids(monkeypatch):
    _clear_creds(monkeypatch)
    monkeypatch.setenv("FACEBOOK_INGEST_ENABLED", "true")
    monkeypatch.setenv("FACEBOOK_API_TOKEN", "tok")
    # Enabled + token but no authorized group ids -> still no-op.
    conn = FacebookGroupsConnector()
    assert conn.is_configured() is False
    assert conn.fetch() == []


def test_get_connector_maps_social_to_dedicated_classes(monkeypatch):
    _clear_creds(monkeypatch)
    assert isinstance(get_connector("linkedin"), LinkedInConnector)
    assert isinstance(get_connector("facebook_groups"), FacebookGroupsConnector)
    assert isinstance(get_connector("bsale"), ApifyConnector)


# --- Apify dataset mapping (mocked payload, no HTTP) ------------------------

def test_apify_map_items_builds_source_items():
    conn = ApifyConnector("bsale")
    dataset = [
        {
            "title": "Established Cafe for Sale",
            "description": "Profitable cafe in Sydney with manual bookkeeping.",
            "url": "https://www.bsale.com.au/listing/555",
            "asking_price": 750000,
        },
        {"name": "No-desc listing", "id": "777"},  # only a name + bare id
        {"nothing_useful": True},  # no recognizable signal -> skipped
        "not-a-dict",  # ignored
    ]
    items = conn.map_items(dataset)
    assert len(items) == 2
    assert all(isinstance(i, SourceItem) for i in items)

    first = items[0]
    assert first.source_name == "Bsale"
    assert first.source_type == SourceType.marketplace.value
    # A full URL is carried through unchanged.
    assert first.external_listing_id_or_url == "https://www.bsale.com.au/listing/555"
    assert "cafe" in first.raw_text.lower()
    # raw_text always embeds a JSON dump of the full record.
    assert '"asking_price":750000' in first.raw_text
    assert first.structured is not None
    assert first.structured.get("asking_price") == 750000

    second = items[1]
    # The human-readable name is present in the blob ...
    assert "No-desc listing" in second.raw_text
    # ... and a bare id is combined with the source base_url into a full URL.
    assert second.external_listing_id_or_url == "https://www.bsale.com.au/777"
    # The full record is always preserved as a JSON dump.
    assert '"id":"777"' in second.raw_text


def test_apify_fetch_maps_dataset_with_mocked_http(monkeypatch):
    """ApifyConnector.fetch() maps a mocked dataset list (no real network)."""

    _clear_creds(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN", "secret-token")
    monkeypatch.setenv("APIFY_ACTOR_BSALE", "acme/bsale-actor")

    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"title": "Manufacturing business", "url": "https://www.bsale.com.au/listing/1"},
                {"heading": "Bookkeeping firm", "listingId": "abc-99"},
            ]

    def _fake_post(url, params=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["token"] = (params or {}).get("token")
        return _FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", _fake_post)

    conn = ApifyConnector("bsale")
    assert conn.is_configured() is True
    items = conn.fetch()

    assert "acme~bsale-actor" in captured["url"]  # actor id slash -> tilde
    assert captured["token"] == "secret-token"
    assert len(items) == 2
    assert all(isinstance(i, SourceItem) for i in items)
    assert items[0].external_listing_id_or_url == "https://www.bsale.com.au/listing/1"
    # A bare id resolves against the source base_url.
    assert items[1].external_listing_id_or_url == "https://www.bsale.com.au/abc-99"
    assert "Bookkeeping firm" in items[1].raw_text


def test_apify_fetch_via_default_actor(monkeypatch):
    """A single shared APIFY_DEFAULT_ACTOR makes a source live without its own actor."""

    _clear_creds(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN", "secret-token")
    monkeypatch.setenv("APIFY_DEFAULT_ACTOR", "acme/shared-actor")
    monkeypatch.delenv("APIFY_ACTOR_RESOLVE", raising=False)

    conn = ApifyConnector("resolve")
    assert conn.is_configured() is True
    assert conn.actor_source == "default"

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"title": "Capital raise opportunity", "url": "https://www.resolve.com.au/x"}]

    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse())
    items = conn.fetch()
    assert len(items) == 1
    assert items[0].source_name == "Resolve Marketplace"
