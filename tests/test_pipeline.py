"""Task 12.1 - full pipeline integration (covers P6, P15 at integration level)."""

from app.config import load_thesis_config
from app.pipeline import process_batch
from app.sample_data import sample_batch
from app.validator import is_strict_valid_json

CFG = load_thesis_config({"current_year": 2025, "current_date": "2025-06-01"})


def test_mixed_batch_produces_valid_output_with_thesis_match():
    out = process_batch(sample_batch(), CFG)
    assert is_strict_valid_json(out)
    assert len(out.deals) >= 4
    for d in out.deals:
        assert d.source_name
        assert d.external_listing_id_or_url
        assert d.thesis_match is not None
        assert d.thesis_match.deal_id == d.deal_id


def test_contacts_have_source_provenance():
    out = process_batch(sample_batch(), CFG)
    for c in out.contacts:
        assert c.source_name
        assert c.source_type is not None


def test_determinism_identical_output():
    a = process_batch(sample_batch(), CFG)
    b = process_batch(sample_batch(), CFG)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_empty_batch_valid_output():
    out = process_batch([], CFG)
    assert is_strict_valid_json(out)
    assert out.deals == []
    assert out.summary.core_thesis_deal_count == 0
