"""Tests for the Apify ACTOR_REGISTRY, run_actor, and the live-sync routine.

All tests run with NO real network: ``run_actor`` is exercised against a
monkeypatched ``requests.post``, and ``run_live_sync`` is exercised against a
monkeypatched ``run_actor`` that returns canned dataset items.
"""

from __future__ import annotations

import json

import pytest

from app import store
from app.actors import (
    ACTOR_REGISTRY,
    CATEGORY_AU_DIRECTORIES,
    CATEGORY_AU_GLOBAL_BFS,
    CATEGORY_BIZBUYSELL,
    CATEGORY_LINKEDIN,
    CATEGORY_MA_INTEL,
    CATEGORY_NEWS,
    actor_input_env_var,
    linkedin_actors,
    resolve_actor_input,
)
from app.models import SourceItem, SourceType


# --- Registry shape ---------------------------------------------------------


def test_registry_has_22_entries():
    assert len(ACTOR_REGISTRY) == 22


def test_every_entry_has_required_fields():
    seen_keys = set()
    for e in ACTOR_REGISTRY:
        assert e.name and isinstance(e.name, str)
        assert e.actor_id and "~" in e.actor_id  # Apify tilde form
        assert e.source_key and e.source_key == e.source_key.lower()
        assert isinstance(e.source_type, SourceType)
        assert e.category
        assert isinstance(e.input, dict)
        assert isinstance(e.is_linkedin, bool)
        seen_keys.add(e.source_key)
    # Source keys are unique across the registry.
    assert len(seen_keys) == 22


def test_category_counts():
    by_cat: dict[str, int] = {}
    for e in ACTOR_REGISTRY:
        by_cat[e.category] = by_cat.get(e.category, 0) + 1
    assert by_cat[CATEGORY_AU_GLOBAL_BFS] == 5
    assert by_cat[CATEGORY_BIZBUYSELL] == 4
    assert by_cat[CATEGORY_AU_DIRECTORIES] == 3
    assert by_cat[CATEGORY_LINKEDIN] == 4
    assert by_cat[CATEGORY_MA_INTEL] == 3
    assert by_cat[CATEGORY_NEWS] == 3


def test_source_type_mapping_is_correct():
    by_id = {e.actor_id: e for e in ACTOR_REGISTRY}
    # Category 1 + 2 -> marketplace
    assert by_id["mai_amm~australia-business-for-sale-scraper"].source_type is SourceType.marketplace
    assert by_id["scrapesage~bizbuysell-scraper"].source_type is SourceType.marketplace
    # Category 3 directories -> broker_directory, ASIC -> chamber_directory
    assert by_id["proscraper~australia-business-scraper"].source_type is SourceType.broker_directory
    assert by_id["datafoundry~ypau"].source_type is SourceType.broker_directory
    assert by_id["parseforge~australia-asic-scraper"].source_type is SourceType.chamber_directory
    # Category 4 -> social
    assert by_id["harvestapi~linkedin-post-search"].source_type is SourceType.social
    # Category 5 + 6 -> news
    assert by_id["datahyena~company-acquisitions-ma"].source_type is SourceType.news
    assert by_id["nexgendata~google-news-scraper"].source_type is SourceType.news


def test_exactly_four_linkedin_actors_flagged():
    li = linkedin_actors()
    assert len(li) == 4
    assert all(a.is_linkedin for a in li)
    assert all(a.source_type is SourceType.social for a in li)
    ids = {a.actor_id for a in li}
    assert ids == {
        "harvestapi~linkedin-post-search",
        "harvestapi~linkedin-profile-posts",
        "harvestapi~linkedin-company-posts",
        "datadoping~linkedin-posts-search-scraper",
    }


def test_default_inputs_match_spec_examples():
    by_id = {e.actor_id: e for e in ACTOR_REGISTRY}
    assert by_id["solidcode~businesses-for-sale-scraper"].input == {
        "country": "Australia", "maxResults": 200, "minCashFlow": 250000,
    }
    assert by_id["scrapesage~bizbuysell-scraper"].input["maxItems"] == 100
    assert by_id["harvestapi~linkedin-post-search"].input["postedLimit"] == "past-week"


# --- Per-actor input override -----------------------------------------------


def test_resolve_actor_input_uses_default_without_env(monkeypatch):
    entry = ACTOR_REGISTRY[0]
    monkeypatch.delenv(actor_input_env_var(entry.source_key), raising=False)
    assert resolve_actor_input(entry) == entry.input
    # Returns a copy, not the same object (so mutation can't corrupt the registry).
    assert resolve_actor_input(entry) is not entry.input


def test_resolve_actor_input_honours_env_override(monkeypatch):
    entry = ACTOR_REGISTRY[0]
    override = {"maxItems": 5, "location": "Sydney"}
    monkeypatch.setenv(actor_input_env_var(entry.source_key), json.dumps(override))
    assert resolve_actor_input(entry) == override


def test_resolve_actor_input_ignores_malformed_env(monkeypatch):
    entry = ACTOR_REGISTRY[0]
    monkeypatch.setenv(actor_input_env_var(entry.source_key), "{not-json")
    assert resolve_actor_input(entry) == entry.input


# --- run_actor (mocked HTTP) ------------------------------------------------


def test_run_actor_builds_run_sync_url_and_body(monkeypatch):
    from app.connectors import apify_connector

    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"title": "Deal A", "url": "https://x/a"}, "junk", {"id": "b"}]

    def _fake_post(url, params=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["params"] = params
        captured["body"] = json
        captured["timeout"] = timeout
        return _FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", _fake_post)

    body = {"maxItems": 7, "location": "Australia"}
    items = apify_connector.run_actor("mai_amm~australia-business-for-sale-scraper", body, "tok-123", 30)

    assert captured["url"] == (
        "https://api.apify.com/v2/acts/"
        "mai_amm~australia-business-for-sale-scraper/run-sync-get-dataset-items"
    )
    assert captured["params"] == {"token": "tok-123"}
    assert captured["body"] == body
    assert captured["timeout"] == 30
    # Returns only dict records (the "junk" string is dropped).
    assert items == [{"title": "Deal A", "url": "https://x/a"}, {"id": "b"}]


def test_run_actor_normalizes_slash_actor_id(monkeypatch):
    from app.connectors import apify_connector

    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    def _fake_post(url, params=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        return _FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", _fake_post)
    apify_connector.run_actor("owner/name", {}, "tok")
    assert "owner~name" in captured["url"]


def test_run_actor_error_path_returns_empty(monkeypatch):
    from app.connectors import apify_connector

    def _boom(*a, **k):
        raise RuntimeError("network down")

    import requests

    monkeypatch.setattr(requests, "post", _boom)
    assert apify_connector.run_actor("a~b", {}, "tok") == []


def test_run_actor_without_token_returns_empty():
    from app.connectors import apify_connector

    assert apify_connector.run_actor("a~b", {}, "") == []


# --- run_live_sync (mocked run_actor) ---------------------------------------


@pytest.fixture()
def live_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "live_sync.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    for var in ("APIFY_TOKEN", "APIFY_DEFAULT_ACTOR", "APIFY_ACTOR"):
        monkeypatch.delenv(var, raising=False)
    store.init_db()
    return str(tmp_path / "live_sync.db")


def _fake_dataset(actor_id, run_input, token, timeout=120):
    """Return canned dataset items keyed off the actor kind (no network)."""

    if "linkedin" in actor_id:
        return [
            {
                "id": f"post::{actor_id}",
                "author_name": "Jane Broker",
                "author_linkedin_url": "https://www.linkedin.com/in/jane",
                "text": "Manufacturing business for sale in Sydney.",
                "created_at": "2026-01-01T00:00:00Z",
                "url": f"https://www.linkedin.com/posts/{actor_id}",
            }
        ]
    return [
        {
            "title": "Established Manufacturing Business",
            "url": f"https://example.com/{actor_id}",
            "description": "Profitable manufacturer with automation upside.",
            "asking_price": 5_000_000,
        }
    ]


def test_run_live_sync_without_token_skips_all_no_snapshot(live_db, monkeypatch):
    from app import scheduler

    result = scheduler.run_live_sync()
    assert result["processed"] is False
    assert result["item_count"] == 0

    jobs = {j["source_key"]: j for j in store.get_job_statuses()}
    assert len(jobs) == len(ACTOR_REGISTRY)
    assert all(j["status"] == "skipped" for j in jobs.values())
    assert all(j["message"] == "skipped: no API key" for j in jobs.values())
    # No live snapshot was created (kind unchanged).
    assert store.load_latest_live_snapshot() is None


def test_run_live_sync_collects_deals_and_linkedin_posts(live_db, monkeypatch):
    from app import scheduler
    from app.connectors import apify_connector

    monkeypatch.setenv("APIFY_TOKEN", "secret-token")
    monkeypatch.setattr(apify_connector, "run_actor", _fake_dataset)

    result = scheduler.run_live_sync()
    assert result["processed"] is True
    # 18 non-linkedin actors each yield 1 source item.
    assert result["item_count"] == 18
    # 4 linkedin actors each yield 1 post.
    assert result["linkedin_post_count"] == 4
    assert result["produced_deal_count"] >= 1

    # A live_sync snapshot now exists with linkedin posts attached.
    snap = store.load_latest_live_snapshot()
    assert snap is not None
    assert snap["kind"] == "live_sync"
    assert snap["synced_at"]
    assert len(snap["deals"]) == 18
    assert len(snap["linkedin_posts"]) == 4

    # Per-actor job messages set.
    jobs = {j["source_key"]: j for j in store.get_job_statuses()}
    assert len(jobs) == len(ACTOR_REGISTRY)
    assert all(j["status"] == "success" for j in jobs.values())
    assert all(j["message"] == "success: 1 items" for j in jobs.values())


def test_run_live_sync_marks_zero_items(live_db, monkeypatch):
    from app import scheduler
    from app.connectors import apify_connector

    monkeypatch.setenv("APIFY_TOKEN", "secret-token")
    monkeypatch.setattr(apify_connector, "run_actor", lambda *a, **k: [])

    result = scheduler.run_live_sync()
    assert result["processed"] is True
    assert result["item_count"] == 0
    jobs = {j["source_key"]: j for j in store.get_job_statuses()}
    assert all(j["message"] == "fetched 0 items" for j in jobs.values())
    # A live snapshot still gets written (empty deals), kind=live_sync.
    snap = store.load_latest_live_snapshot()
    assert snap is not None and snap["kind"] == "live_sync"


def test_run_live_sync_one_actor_error_does_not_crash(live_db, monkeypatch):
    from app import scheduler
    from app.connectors import apify_connector

    monkeypatch.setenv("APIFY_TOKEN", "secret-token")

    def _maybe_boom(actor_id, run_input, token, timeout=120):
        if actor_id == "memo23~businessesforsale-scraper":
            raise RuntimeError("boom")
        return _fake_dataset(actor_id, run_input, token, timeout)

    # run_actor itself swallows errors, but map failures must be contained too;
    # simulate a raising run_actor to exercise the per-actor error branch.
    monkeypatch.setattr(apify_connector, "run_actor", _maybe_boom)

    result = scheduler.run_live_sync()
    assert result["processed"] is True
    jobs = {j["source_key"]: j for j in store.get_job_statuses()}
    errored = [j for j in jobs.values() if j["status"] == "error"]
    assert len(errored) == 1
    assert errored[0]["message"].startswith("error:")
