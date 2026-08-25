"""Tests for app.db: persisting an upload's pipeline result and reading it back."""

from __future__ import annotations

from app import db
from app.config import load_thesis_config
from app.models import SourceItem
from app.pipeline import process_batch


def _process_one(raw_text: str, source_name: str = "teaser.pdf"):
    item = SourceItem(source_name=source_name, source_type="document_upload", raw_text=raw_text)
    output = process_batch([item], load_thesis_config())
    company_name_by_id = {c.company_id: c.name for c in output.companies}
    return output, company_name_by_id


def setup_module(_module) -> None:
    db.init_db()


def test_save_upload_result_round_trips_document_and_deals():
    output, company_name_by_id = _process_one(
        "Established Melbourne bookkeeping firm, 12 years trading, revenue $900,000, "
        "EBITDA $300,000, asking price $1,200,000."
    )
    doc = db.save_upload_result(
        filename="bookkeeping-teaser.pdf",
        content_type="application/pdf",
        file_size_bytes=1234,
        raw_text="Established Melbourne bookkeeping firm...",
        output=output,
        company_name_by_id=company_name_by_id,
    )

    assert doc.id
    assert doc.filename == "bookkeeping-teaser.pdf"
    assert len(doc.deals) == len(output.deals)

    fetched = db.get_document(doc.id)
    assert fetched is not None
    assert fetched.filename == "bookkeeping-teaser.pdf"
    assert len(fetched.deals) == len(output.deals)


def test_list_documents_orders_most_recent_first():
    output, names = _process_one("Small IT services shop, unknown financials.", "a.pdf")
    first = db.save_upload_result(
        filename="a.pdf", content_type=None, file_size_bytes=10,
        raw_text="a", output=output, company_name_by_id=names,
    )
    output2, names2 = _process_one("Another IT services shop, unknown financials.", "b.pdf")
    second = db.save_upload_result(
        filename="b.pdf", content_type=None, file_size_bytes=10,
        raw_text="b", output=output2, company_name_by_id=names2,
    )

    docs = db.list_documents(limit=2)
    ids = [d.id for d in docs]
    assert ids.index(second.id) < ids.index(first.id)


def test_list_deal_records_can_filter_by_classification():
    output, names = _process_one(
        "Manufacturing business, 15 years trading, revenue $5,000,000, EBITDA $1,200,000.",
        "manufacturing.pdf",
    )
    db.save_upload_result(
        filename="manufacturing.pdf", content_type=None, file_size_bytes=10,
        raw_text="manufacturing business", output=output, company_name_by_id=names,
    )

    all_rows = db.list_deal_records()
    assert len(all_rows) >= 1

    classifications = {row.classification for row in all_rows}
    for cls in classifications:
        filtered = db.list_deal_records(classification=cls)
        assert all(row.classification == cls for row in filtered)
