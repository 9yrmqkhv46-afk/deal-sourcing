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
    CATEGORY_COMPANY_REGISTRIES,
    CATEGORY_DEAL_MARKETPLACES_EXTRA,
    CATEGORY_LINKEDIN,
    CATEGORY_LOCAL_DISCOVERY,
    CATEGORY_MA_INTEL,
    CATEGORY_NEWS,
    CATEGORY_SOCIAL_SEARCH,
    actor_input_env_var,
    linkedin_actors,
    resolve_actor_input,
)
from app.models import SourceItem, SourceType


# --- Registry shape ---------------------------------------------------------


def test_registry_has_31_entries():
    assert len(ACTOR_REGISTRY) == 31


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
    assert len(seen_keys) == 31


def test_category_counts():
    by_cat: dict[str, int] = {}
    for e in ACTOR_REGISTRY:
        by_cat[e.category] = by_cat.get(e.category, 0) + 1
    assert by_cat[CATEGORY_AU_GLOBAL_BFS] == 6
    assert by_cat[CATEGORY_BIZBUYSELL] == 4
    assert by_cat[CATEGORY_AU_DIRECTORIES] == 3
    assert by_cat[CATEGORY_LINKEDIN] == 4
    assert by_cat[CATEGORY_MA_INTEL] == 3
    assert by_cat[CATEGORY_NEWS] == 3
    assert by_cat[CATEGORY_DEAL_MARKETPLACES_EXTRA] == 3
    assert by_cat[CATEGORY_COMPANY_REGISTRIES] == 1
    assert by_cat[CATEGORY_LOCAL_DISCOVERY] == 1
    assert by_cat[CATEGORY_SOCIAL_SEARCH] == 3


def test_no_bulk_linkedin_people_scrapers_present():
    """Compliance boundary: no bulk LinkedIn people/profile/employee scrapers."""
    forbidden = (
        "profile-scraper",
        "company-employees",
        "people-scraper",
        "employees-bulk",
    )
    for e in ACTOR_REGISTRY:
        for token in forbidden:
            assert token not in e.actor_id, f"forbidden actor present: {e.actor_id}"


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
    # maxResults lowered to 50 to stay within run-sync limits; minCashFlow unchanged.
    # "country" was dropped after Apify rejected "Australia" with a 400
    # (constrained enum, real allowed values unknown) - see app/actors.py.
    assert by_id["solidcode~businesses-for-sale-scraper"].input == {
        "maxResults": 50, "minCashFlow": 250000,
    }
    # maxItems lowered from 100 -> 50 to avoid run-sync 408/413.
    assert by_id["scrapesage~bizbuysell-scraper"].input["maxItems"] == 50
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


def _fake_result(actor_id, run_input, token, timeout=120):
    """Wrap :func:`_fake_dataset` in a successful ActorRunResult (no network)."""

    from app.connectors.apify_connector import ActorRunResult

    return ActorRunResult(
        items=_fake_dataset(actor_id, run_input, token, timeout),
        ok=True,
        error=None,
        status_code=200,
    )


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
    monkeypatch.setattr(apify_connector, "run_actor_result", _fake_result)

    result = scheduler.run_live_sync()
    assert result["processed"] is True
    # 27 non-linkedin actors each yield 1 source item.
    assert result["item_count"] == 27
    # 4 linkedin actors each yield 1 post.
    assert result["linkedin_post_count"] == 4
    assert result["produced_deal_count"] >= 1

    # A live_sync snapshot now exists with linkedin posts attached.
    snap = store.load_latest_live_snapshot()
    assert snap is not None
    assert snap["kind"] == "live_sync"
    assert snap["synced_at"]
    assert len(snap["deals"]) == 27
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
    monkeypatch.setattr(
        apify_connector, "run_actor_result",
        lambda *a, **k: apify_connector.ActorRunResult(items=[], ok=True, error=None, status_code=200),
    )

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

    def _maybe_error(actor_id, run_input, token, timeout=120):
        if actor_id == "memo23~businessesforsale-scraper":
            return apify_connector.ActorRunResult(
                items=[], ok=False,
                error="401 Unauthorized: token invalid", status_code=401,
            )
        return _fake_result(actor_id, run_input, token, timeout)

    monkeypatch.setattr(apify_connector, "run_actor_result", _maybe_error)

    result = scheduler.run_live_sync()
    assert result["processed"] is True
    # The aggregate surfaces the error count + a sample of messages.
    assert result["error_count"] == 1
    assert any("401 Unauthorized" in m for m in result["errors"])

    jobs = {j["source_key"]: j for j in store.get_job_statuses()}
    errored = [j for j in jobs.values() if j["status"] == "error"]
    assert len(errored) == 1
    # The REAL Apify error (status code + reason) is surfaced, not a generic one.
    assert errored[0]["message"] == "401 Unauthorized: token invalid"
    # All other actors still succeeded (one failure never aborts the others).
    assert sum(1 for j in jobs.values() if j["status"] == "success") == len(ACTOR_REGISTRY) - 1
    # A snapshot is still written despite the one failure.
    snap = store.load_latest_live_snapshot()
    assert snap is not None and snap["kind"] == "live_sync"


def test_run_live_sync_all_actors_error_keeps_previous_snapshot(live_db, monkeypatch):
    """Reproduces an account-level outage (e.g. Apify monthly usage cap):
    every actor fails, so the sync must NOT overwrite a previously-good live
    snapshot with an empty one."""

    from app import scheduler
    from app.connectors import apify_connector

    monkeypatch.setenv("APIFY_TOKEN", "secret-token")
    monkeypatch.setattr(apify_connector, "run_actor_result", _fake_result)

    first = scheduler.run_live_sync()
    assert first["processed"] is True
    good_snap = store.load_latest_live_snapshot()
    assert good_snap is not None and len(good_snap["deals"]) == 27

    def _all_403(actor_id, run_input, token, timeout=120):
        return apify_connector.ActorRunResult(
            items=[], ok=False,
            error='403 forbidden: token lacks access: monthly usage hard limit exceeded',
            status_code=403,
        )

    monkeypatch.setattr(apify_connector, "run_actor_result", _all_403)

    result = scheduler.run_live_sync()
    assert result["processed"] is False
    assert result["error_count"] == len(ACTOR_REGISTRY)

    # The earlier good snapshot is still what's being served, untouched.
    snap = store.load_latest_live_snapshot()
    assert snap is not None
    assert snap["synced_at"] == good_snap["synced_at"]
    assert len(snap["deals"]) == 27


def test_run_live_sync_mapping_error_is_contained(live_db, monkeypatch):
    """A raising run_actor_result (defensive branch) is contained as an error."""

    from app import scheduler
    from app.connectors import apify_connector

    monkeypatch.setenv("APIFY_TOKEN", "secret-token")

    def _maybe_boom(actor_id, run_input, token, timeout=120):
        if actor_id == "memo23~businessesforsale-scraper":
            raise RuntimeError("boom")
        return _fake_result(actor_id, run_input, token, timeout)

    monkeypatch.setattr(apify_connector, "run_actor_result", _maybe_boom)

    result = scheduler.run_live_sync()
    assert result["processed"] is True
    jobs = {j["source_key"]: j for j in store.get_job_statuses()}
    errored = [j for j in jobs.values() if j["status"] == "error"]
    assert len(errored) == 1
    assert errored[0]["message"].startswith("error:")


# --- run_actor_result (mocked HTTP) -----------------------------------------


def _resp(status_code=None, json_data=None, text=""):
    class _R:
        def __init__(self):
            self.status_code = status_code
            self.text = text

        def json(self):
            if json_data is None:
                raise ValueError("no json")
            return json_data

    return _R()


def test_run_actor_result_success(monkeypatch):
    from app.connectors import apify_connector

    items = [{"title": "Deal A", "url": "https://x/a"}, "junk", {"id": "b"}]
    monkeypatch.setattr(
        "requests.post", lambda *a, **k: _resp(status_code=200, json_data=items)
    )
    result = apify_connector.run_actor_result("a~b", {}, "tok", 30)
    assert result.ok is True
    assert result.error is None
    assert result.status_code == 200
    # Only dict records survive.
    assert result.items == [{"title": "Deal A", "url": "https://x/a"}, {"id": "b"}]
    # The thin wrapper returns just the items list.
    monkeypatch.setattr(
        "requests.post", lambda *a, **k: _resp(status_code=200, json_data=items)
    )
    assert apify_connector.run_actor("a~b", {}, "tok") == result.items


def test_run_actor_result_401(monkeypatch):
    from app.connectors import apify_connector

    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _resp(status_code=401, text="token invalid"),
    )
    result = apify_connector.run_actor_result("a~b", {}, "tok")
    assert result.ok is False
    assert result.status_code == 401
    assert result.items == []
    assert "401" in result.error and "Unauthorized" in result.error
    assert "token invalid" in result.error


def test_run_actor_result_404_includes_actor_id(monkeypatch):
    from app.connectors import apify_connector

    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _resp(status_code=404, text="not found"),
    )
    result = apify_connector.run_actor_result("owner/missing", {}, "tok")
    assert result.ok is False
    assert result.status_code == 404
    # Actor id (tilde form) is embedded in the message.
    assert "owner~missing" in result.error


def test_run_actor_result_413(monkeypatch):
    from app.connectors import apify_connector

    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _resp(status_code=413, text="payload too large"),
    )
    result = apify_connector.run_actor_result("a~b", {}, "tok")
    assert result.ok is False
    assert result.status_code == 413
    assert "dataset too large" in result.error


def test_run_actor_result_timeout(monkeypatch):
    from app.connectors import apify_connector

    class _Timeout(Exception):
        pass

    def _boom(*a, **k):
        raise _Timeout("read timed out")

    monkeypatch.setattr("requests.post", _boom)
    result = apify_connector.run_actor_result("a~b", {}, "tok", 45)
    assert result.ok is False
    assert result.status_code is None
    assert result.error == "timeout after 45s"
    # Wrapper still returns [] on failure.
    monkeypatch.setattr("requests.post", _boom)
    assert apify_connector.run_actor("a~b", {}, "tok", 45) == []


def test_run_actor_result_connection_error(monkeypatch):
    from app.connectors import apify_connector

    def _boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr("requests.post", _boom)
    result = apify_connector.run_actor_result("a~b", {}, "tok")
    assert result.ok is False
    assert result.error.startswith("network error:")


def test_run_actor_result_without_token():
    from app.connectors import apify_connector

    result = apify_connector.run_actor_result("a~b", {}, "")
    assert result.ok is False
    assert result.items == []
    assert result.status_code is None
