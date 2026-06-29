"""Task 5.1 - source handlers with representative payloads."""

from app.config import load_thesis_config
from app.models import SourceItem
from app.router import route

CFG = load_thesis_config()


def _route(source_name, source_type, raw_text, structured=None):
    item = SourceItem(
        source_name=source_name,
        source_type=source_type,
        raw_text=raw_text,
        structured=structured,
    )
    return route(item, CFG)


def test_marketplace_extracts_listing_and_broker_contact():
    rf = _route(
        "scaling.com.au",
        "marketplace",
        "Packaging manufacturer for sale",
        {
            "title": "Packaging Co",
            "url": "https://scaling.com.au/x",
            "asking_price": 12_000_000,
            "revenue": 4_000_000,
            "contacts": [{"person_or_org_name": "Broker B", "role_or_title": "Broker"}],
        },
    )
    assert rf.deal_type == "sale"
    assert rf.asking_price == 12_000_000
    assert rf.revenue == 4_000_000
    assert rf.contacts[0]["person_or_org_name"] == "Broker B"


def test_marketplace_detects_franchise():
    rf = _route(
        "scaling.com.au",
        "marketplace",
        "Great franchise opportunity in QLD",
        {"title": "Franchise X"},
    )
    assert rf.is_franchise is True
    assert rf.deal_type == "franchise"


def test_insolvency_sets_distress_and_practitioner():
    rf = _route(
        "ASIC",
        "insolvency_platform",
        "Liquidator appointed",
        {"title": "Distressed Co", "contacts": [{"person_or_org_name": "Liq P"}]},
    )
    assert rf.deal_type == "distress"
    assert rf.contacts[0]["role_or_title"] == "Practitioner"


def test_chamber_extracts_target_and_official():
    rf = _route(
        "Chamber AU",
        "chamber_directory",
        "Member firm bookkeeping",
        {"title": "Member Firm", "contacts": [{"person_or_org_name": "Official O"}]},
    )
    assert rf.contacts[0]["role_or_title"] == "Association Official"


def test_social_does_not_treat_claims_as_financials():
    rf = _route(
        "LinkedIn",
        "social",
        "We make millions! Huge revenue!",
        {"title": "Hype Co", "revenue": 9_999_999, "asking_price": 5_000_000},
    )
    # social handler must NOT copy financial figures
    assert rf.revenue is None
    assert rf.asking_price is None


def test_handlers_do_not_invent_missing_fields():
    rf = _route("scaling.com.au", "marketplace", "Bare listing with no structure")
    assert rf.asking_price is None
    assert rf.revenue is None
    assert rf.ebitda is None
