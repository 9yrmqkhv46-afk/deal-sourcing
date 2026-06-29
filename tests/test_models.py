"""Task 1.1 - model construction and null defaults."""

import pytest
from pydantic import ValidationError

from app.models import (
    Classification,
    Company,
    Contact,
    Deal,
    Founder,
    FounderRole,
    SourceItem,
    SourceType,
    ThesisMatch,
)


def test_company_minimal_defaults_to_null():
    c = Company(name="Acme", country="Australia")
    assert c.sector is None
    assert c.founded_year is None
    assert c.age_years is None
    assert c.banned_sector_flag is False


def test_deal_minimal_required_fields_and_null_defaults():
    d = Deal(
        source_name="scaling.com.au",
        source_type=SourceType.marketplace,
        external_listing_id_or_url="https://scaling.com.au/x",
        title="Listing",
    )
    assert d.asking_price is None
    assert d.revenue is None
    assert d.deal_size_bucket.value == "unknown"
    assert isinstance(d.thesis_match, ThesisMatch)
    assert d.thesis_match.classification is Classification.reject


def test_deal_requires_currency_companion_for_revenue():
    with pytest.raises(ValidationError):
        Deal(
            source_name="s",
            source_type=SourceType.marketplace,
            external_listing_id_or_url="u",
            title="t",
            revenue=1_000_000,  # missing revenue_currency
        )


def test_deal_accepts_amount_with_currency():
    d = Deal(
        source_name="s",
        source_type=SourceType.marketplace,
        external_listing_id_or_url="u",
        title="t",
        revenue=1_000_000,
        revenue_currency="AUD",
        ebitda=200_000,
        ebitda_currency="AUD",
    )
    assert d.revenue == 1_000_000
    assert d.revenue_currency == "AUD"


def test_founder_tenure_optional():
    f = Founder(name="Jane", role=FounderRole.Founder)
    assert f.tenure_years is None
    assert f.start_year is None


def test_contact_requires_source_provenance():
    c = Contact(
        person_or_org_name="Broker Bob",
        source_name="dir",
        source_type=SourceType.broker_directory,
    )
    assert c.priority_reason is None
    assert c.source_name == "dir"


def test_source_item_requires_core_fields():
    with pytest.raises(ValidationError):
        SourceItem(source_name="x", source_type="marketplace")  # missing raw_text
