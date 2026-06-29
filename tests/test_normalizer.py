"""Tasks 6.1 & 6.3 - normalization, inference, size bucketing, recency."""

import datetime as _dt

from app.config import load_thesis_config
from app.handlers import RawFields
from app.models import Deal, DealSizeBucket, SourceType, UNKNOWN_DATE
from app.normalizer import (
    infer_deal_size_bucket,
    infer_recency,
    normalize_company,
    normalize_deal,
    normalize_founders,
)

CFG = load_thesis_config({"current_year": 2025, "current_date": "2025-06-01"})


def _rf(**over):
    base = dict(
        source_name="scaling.com.au",
        source_type="marketplace",
        external_listing_id_or_url="https://x/1",
        title="Co",
        company={"name": "Co", "country": "Australia"},
    )
    base.update(over)
    return RawFields(**base)


def test_age_years_computed_from_founded_year():
    rf = _rf(company={"name": "Co", "country": "Australia", "founded_year": 2010})
    c = normalize_company(rf, CFG)
    assert c.age_years == 15


def test_age_years_null_without_founded_year():
    c = normalize_company(_rf(), CFG)
    assert c.age_years is None


def test_range_revenue_becomes_midpoint_flagged_estimated():
    rf = _rf(revenue=(2_000_000, 4_000_000), revenue_currency="AUD")
    company = normalize_company(rf, CFG)
    d = normalize_deal(rf, company, CFG)
    assert d.revenue == 3_000_000
    assert d.revenue_estimated is True


def test_exact_revenue_not_estimated():
    rf = _rf(revenue=3_000_000, revenue_currency="AUD")
    d = normalize_deal(rf, normalize_company(rf, CFG), CFG)
    assert d.revenue == 3_000_000
    assert d.revenue_estimated is False


def test_currency_pairing_populated_when_amount_present():
    rf = _rf(asking_price=12_000_000)
    d = normalize_deal(rf, normalize_company(rf, CFG), CFG)
    assert d.asking_price_currency == "AUD"


def test_franchise_tagging():
    rf = _rf(is_franchise=True)
    d = normalize_deal(rf, normalize_company(rf, CFG), CFG)
    assert d.is_franchise is True
    assert d.deal_type.value == "franchise"
    assert "unit-economics" in (d.competitive_notes or "")


def test_founder_tenure_derived_only_with_start_year():
    rf = _rf(founders=[{"name": "A", "role": "Founder", "start_year": 2000}, {"name": "B", "role": "Director"}])
    founders = normalize_founders(rf, CFG)
    assert founders[0].tenure_years == 25
    assert founders[1].tenure_years is None


def _deal_with_ev(asking=None, ebitda=None):
    kwargs = dict(
        source_name="s",
        source_type=SourceType.marketplace,
        external_listing_id_or_url="u",
        title="t",
    )
    if asking is not None:
        kwargs.update(asking_price=asking, asking_price_currency="AUD")
    if ebitda is not None:
        kwargs.update(ebitda=ebitda, ebitda_currency="AUD")
    return Deal(**kwargs)


def test_size_bucket_core_mid():
    assert infer_deal_size_bucket(_deal_with_ev(asking=20_000_000), CFG) is DealSizeBucket.core_mid


def test_size_bucket_just_under_core_is_lower_mid():
    assert infer_deal_size_bucket(_deal_with_ev(asking=9_000_000), CFG) is DealSizeBucket.lower_mid


def test_size_bucket_small():
    assert infer_deal_size_bucket(_deal_with_ev(asking=500_000), CFG) is DealSizeBucket.small


def test_size_bucket_oversized_upper_mid():
    assert infer_deal_size_bucket(_deal_with_ev(asking=80_000_000), CFG) is DealSizeBucket.upper_mid


def test_size_bucket_unknown_without_ev():
    assert infer_deal_size_bucket(_deal_with_ev(), CFG) is DealSizeBucket.unknown


def test_recency_unknown_dates_not_stale():
    listing, last_seen, stale = infer_recency(_rf(), CFG)
    assert listing == UNKNOWN_DATE and last_seen == UNKNOWN_DATE
    assert stale is False


def test_recency_old_date_is_stale():
    rf = _rf(listing_date="2020-01-01", last_seen_at="2020-02-01")
    _, _, stale = infer_recency(rf, CFG)
    assert stale is True


def test_recency_recent_date_not_stale():
    recent = (_dt.date(2025, 6, 1) - _dt.timedelta(days=30)).isoformat()
    rf = _rf(listing_date=recent)
    _, _, stale = infer_recency(rf, CFG)
    assert stale is False
