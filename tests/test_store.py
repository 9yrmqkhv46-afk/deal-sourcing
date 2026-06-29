"""Tests for SQLite persistence (snapshots + sync-job status)."""

import importlib

import pytest

from app import store
from app.pipeline import process_batch
from app.sample_data import sample_batch
from app.validator import REQUIRED_TOP_LEVEL_KEYS


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the store at an isolated temp database for each test."""

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    store.init_db()
    return str(db_file)


def test_init_creates_tables_and_empty_state(temp_db):
    assert store.has_snapshot() is False
    assert store.load_latest_snapshot() is None
    assert store.get_overall_last_sync() is None
    assert store.get_job_statuses() == []


def test_save_and_load_snapshot_round_trip(temp_db):
    output = process_batch(sample_batch())
    store.save_snapshot(output)

    loaded = store.load_latest_snapshot()
    assert loaded is not None
    assert set(loaded.keys()) == REQUIRED_TOP_LEVEL_KEYS
    assert len(loaded["deals"]) == len(output.deals)
    # listing_url survives the round-trip inside deal objects.
    assert all("listing_url" in d for d in loaded["deals"])


def test_latest_snapshot_returns_most_recent(temp_db):
    out1 = process_batch(sample_batch())
    store.save_snapshot(out1)
    out2 = process_batch(sample_batch()[:1])
    store.save_snapshot(out2)
    loaded = store.load_latest_snapshot()
    assert len(loaded["deals"]) == len(out2.deals)


def test_upsert_job_insert_then_update(temp_db):
    store.upsert_job("bsale", "sync:bsale", "running", started_at="2025-01-01T03:00:00+00:00")
    jobs = store.get_job_statuses()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "running"

    store.upsert_job(
        "bsale", "sync:bsale", "success",
        finished_at="2025-01-01T03:01:00+00:00",
        last_sync_at="2025-01-01T03:01:00+00:00",
        item_count=7,
        message="fetched 7 item(s)",
    )
    jobs = store.get_job_statuses()
    assert len(jobs) == 1  # upsert, not insert
    row = jobs[0]
    assert row["status"] == "success"
    assert row["item_count"] == 7
    # started_at preserved across the update via COALESCE.
    assert row["started_at"] == "2025-01-01T03:00:00+00:00"
    assert store.get_overall_last_sync() == "2025-01-01T03:01:00+00:00"


def test_invalid_status_rejected(temp_db):
    with pytest.raises(ValueError):
        store.upsert_job("x", "sync:x", "bogus")
