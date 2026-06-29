"""Task 15.1 - API tests with FastAPI TestClient."""

from fastapi.testclient import TestClient

from app.main import app
from app.sample_data import sample_batch
from app.validator import REQUIRED_TOP_LEVEL_KEYS

client = TestClient(app)


def test_process_returns_strict_json_for_good_batch():
    resp = client.post("/api/process", json={"batch": sample_batch()})
    assert resp.status_code == 200
    payload = resp.json()
    assert set(payload.keys()) == REQUIRED_TOP_LEVEL_KEYS
    assert len(payload["deals"]) >= 4


def test_process_rejects_non_list_batch():
    resp = client.post("/api/process", json={"batch": "not-a-list"})
    assert resp.status_code == 422


def test_process_skips_malformed_items_without_fabrication():
    batch = [
        {"source_name": "scaling.com.au", "source_type": "marketplace", "raw_text": "ok"},
        {"source_name": "", "source_type": "marketplace", "raw_text": "bad"},
    ]
    resp = client.post("/api/process", json={"batch": batch})
    assert resp.status_code == 200
    assert len(resp.json()["deals"]) == 1


def test_sample_endpoint():
    resp = client.get("/api/sample")
    assert resp.status_code == 200
    assert isinstance(resp.json()["batch"], list)


def test_health_endpoint():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_config_overrides_are_injected():
    batch = sample_batch()
    resp = client.post("/api/process", json={"batch": batch, "config": {"current_year": 2025, "current_date": "2025-06-01"}})
    assert resp.status_code == 200
