"""Task 16.1 - the bundled sample batch processes to valid strict JSON.

The bundled sample is a large, multi-source demo batch. These tests assert the
spread of outcomes the dashboard relies on: at least one ``core_thesis`` deal,
at least one ``reject``, banned-sector rejects, and at least one stale deal.
"""

from app.config import load_thesis_config
from app.models import Classification
from app.pipeline import process_batch
from app.sample_data import sample_batch
from app.validator import is_strict_valid_json


def _process():
    return process_batch(sample_batch(), load_thesis_config())


def test_sample_produces_core_and_reject():
    out = _process()
    assert is_strict_valid_json(out)
    classes = {d.thesis_match.classification for d in out.deals}
    assert Classification.core_thesis in classes
    assert Classification.reject in classes


def test_sample_is_large_and_varied():
    out = _process()
    # A rich demo batch so the dashboard and top-lists look meaningful.
    assert len(out.deals) >= 30
    core = sum(1 for d in out.deals if d.thesis_match.classification is Classification.core_thesis)
    adjacent = sum(1 for d in out.deals if d.thesis_match.classification is Classification.adjacent_thesis)
    rejects = sum(1 for d in out.deals if d.thesis_match.classification is Classification.reject)
    assert core >= 1
    assert adjacent >= 1
    assert rejects >= 1
    # Top lists should be populated.
    assert len(out.summary.top_core_thesis_deals) >= 1
    assert len(out.summary.top_contacts_for_outreach) >= 5


def test_sample_includes_required_source_families():
    batch = sample_batch()
    names = {item["source_name"] for item in batch}
    types = {item["source_type"] for item in batch}
    assert "scaling.com.au" in names
    assert "scalingup.com.au" in names
    # Every one of the six source families must be represented.
    assert {
        "marketplace",
        "broker_directory",
        "insolvency_platform",
        "chamber_directory",
        "social",
        "news",
    } <= types


def test_sample_includes_banned_sector_rejects():
    out = _process()
    banned = [c for c in out.companies if c.banned_sector_flag]
    assert len(banned) >= 1
    banned_ids = {c.company_id for c in banned}
    # Every banned-sector company's deal must be rejected.
    banned_deals = [d for d in out.deals if d.company_id in banned_ids]
    assert banned_deals
    for d in banned_deals:
        assert d.thesis_match.classification is Classification.reject


def test_sample_includes_a_stale_deal_excluded_from_top():
    out = _process()
    stale = [d for d in out.deals if d.is_stale]
    assert len(stale) >= 1
    top_ids = {d.deal_id for d in out.summary.top_core_thesis_deals}
    for d in stale:
        assert d.deal_id not in top_ids


def test_sample_includes_unknown_date_deal():
    out = _process()
    assert any(
        d.listing_date == "unknown_date" and d.last_seen_at == "unknown_date"
        for d in out.deals
    )
