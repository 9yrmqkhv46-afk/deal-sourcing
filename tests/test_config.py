"""Task 2.1 - config defaults and source registry."""

from app.config import load_thesis_config, resolve_source_type
from app.models import SourceType


def test_default_thresholds_match_design():
    cfg = load_thesis_config()
    assert cfg.min_trading_years == 6
    assert cfg.min_founder_tenure_years == 20
    assert cfg.ev_core_min == 10_000_000
    assert cfg.ev_core_max == 40_000_000
    assert cfg.ev_absolute_max == 50_000_000
    assert cfg.recency_cutoff_months == 12
    assert cfg.primary_geography == "Australia"
    assert 250_000 <= cfg.min_revenue_usd <= 300_000
    assert 250_000 <= cfg.min_ebitda_usd <= 300_000


def test_scaling_sources_resolve_to_marketplace():
    cfg = load_thesis_config()
    st, known = resolve_source_type("scaling.com.au", "social", cfg)
    assert st is SourceType.marketplace and known
    st2, known2 = resolve_source_type("Listings at scalingup.com.au", "news", cfg)
    assert st2 is SourceType.marketplace and known2


def test_unknown_source_type_reported():
    cfg = load_thesis_config()
    st, known = resolve_source_type("Random Blog", "blog_post", cfg)
    assert known is False


def test_overrides_applied_and_injected():
    cfg = load_thesis_config({"current_year": 2024, "min_trading_years": 8})
    assert cfg.current_year == 2024
    assert cfg.min_trading_years == 8
