"""Task 15.1 - API tests with FastAPI TestClient."""

from fastapi.testclient import TestClient

from app.main import app
from app.sample_data import sample_batch
from app.validator import REQUIRED_TOP_LEVEL_KEYS
from tests.test_extraction import _make_minimal_pdf, _make_minimal_pptx

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


def test_upload_pdf_processes_and_persists():
    pdf_bytes = _make_minimal_pdf("Regional manufacturing business for sale, 18 years trading.")
    resp = client.post(
        "/api/upload", files={"file": ("teaser.pdf", pdf_bytes, "application/pdf")}
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["document_id"]
    assert payload["filename"] == "teaser.pdf"
    assert set(REQUIRED_TOP_LEVEL_KEYS).issubset(payload.keys())
    assert len(payload["deals"]) == 1

    doc_id = payload["document_id"]
    detail = client.get(f"/api/documents/{doc_id}")
    assert detail.status_code == 200
    assert detail.json()["filename"] == "teaser.pdf"
    assert detail.json()["deal_count"] == 1

    listing = client.get("/api/documents")
    assert listing.status_code == 200
    listed = next(d for d in listing.json()["documents"] if d["id"] == doc_id)
    assert listed["deal_count"] == 1
    assert "deals" not in listed

    deals = client.get("/api/deals")
    assert deals.status_code == 200
    assert any(d["document_id"] == doc_id for d in deals.json()["deals"])


def test_upload_pptx_processes_and_persists():
    pptx_bytes = _make_minimal_pptx("Deal teaser", "Bookkeeping firm, revenue $800,000.")
    resp = client.post(
        "/api/upload",
        files={
            "file": (
                "deck.pptx",
                pptx_bytes,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )
    assert resp.status_code == 200
    assert resp.json()["filename"] == "deck.pptx"


def test_upload_rejects_legacy_ppt():
    resp = client.post("/api/upload", files={"file": ("old.ppt", b"binary junk", "application/vnd.ms-powerpoint")})
    assert resp.status_code == 415


def test_upload_rejects_empty_file():
    resp = client.post("/api/upload", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert resp.status_code == 422


def test_documents_detail_404_for_unknown_id():
    resp = client.get("/api/documents/does-not-exist")
    assert resp.status_code == 404
