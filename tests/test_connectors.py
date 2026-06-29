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
        {"name": "No-desc listing", "id": "777"},  # falls back to name as raw_text
        {"nothing_useful": True},  # no raw text -> skipped
        "not-a-dict",  # ignored
    ]
    items = conn.map_items(dataset)
    assert len(items) == 2
    assert all(isinstance(i, SourceItem) for i in items)

    first = items[0]
    assert first.source_name == "Bsale"
    assert first.source_type == SourceType.marketplace.value
    assert first.external_listing_id_or_url == "https://www.bsale.com.au/listing/555"
    assert "cafe" in first.raw_text.lower()
    assert first.structured is not None
    assert first.structured.get("asking_price") == 750000

    second = items[1]
    assert second.raw_text == "No-desc listing"
    assert second.external_listing_id_or_url == "777"
