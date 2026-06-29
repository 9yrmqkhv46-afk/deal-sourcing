"""Task 19 - smoke test the deployable service (covers P17 end-to-end)."""

from fastapi.testclient import TestClient

from app.main import app
from app.sample_data import sample_batch

client = TestClient(app)

REQUIRED_KEYS = {"deals", "companies", "founders", "contacts", "summary"}


def test_dashboard_served_at_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "TransformBiz" in resp.text


def test_static_assets_served():
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_process_sample_returns_exact_top_level_keys():
    resp = client.post("/api/process", json={"batch": sample_batch()})
    assert resp.status_code == 200
    payload = resp.json()
    assert set(payload.keys()) == REQUIRED_KEYS
    s = payload["summary"]
    total = s["core_thesis_deal_count"] + s["adjacent_thesis_deal_count"] + s["reject_count"]
    assert total == len(payload["deals"])
