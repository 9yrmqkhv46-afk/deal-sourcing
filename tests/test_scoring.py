"""Tasks 7.1 & 7.3 - filter evaluation and scoring math."""

from app.config import load_thesis_config
from app.models import Company, Deal, Founder, FounderRole, SourceType
from app.scoring import (
    FilterResults,
    compute_score,
    evaluate_filters,
)

CFG = load_thesis_config({"current_year": 2025, "current_date": "2025-06-01"})


def _company(**over):
    base = dict(name="Co", country="Australia")
    base.update(over)
    return Company(**base)


def _deal(**over):
    base = dict(
        source_name="s",
        source_type=SourceType.marketplace,
        external_listing_id_or_url="u",
        title="t",
    )
    base.update(over)
    return Deal(**base)


# --- Filter tri-state coverage ---

def test_age_filter_true_false_null():
    f_true = evaluate_filters(_company(founded_year=2000), _deal(), [], CFG)
    assert f_true.passes_age_filter is True
    f_false = evaluate_filters(_company(founded_year=2024), _deal(), [], CFG)
    assert f_false.passes_age_filter is False
    f_null = evaluate_filters(_company(), _deal(), [], CFG)
    assert f_null.passes_age_filter is None


def test_sector_filter_banned_is_false():
    c = _company(sector="manufacturing", banned_sector_flag=True)
    assert evaluate_filters(c, _deal(), [], CFG).passes_sector_filter is False


def test_sector_filter_preferred_true_and_unknown_null():
    assert evaluate_filters(_company(sector="manufacturing"), _deal(), [], CFG).passes_sector_filter is True
    assert evaluate_filters(_company(sector=None), _deal(), [], CFG).passes_sector_filter is None


def test_financial_filter_true_false_null():
    d_true = _deal(revenue=1_000_000, revenue_currency="AUD", ebitda=400_000, ebitda_currency="AUD")
    assert evaluate_filters(_company(), d_true, [], CFG).passes_financial_filter is True
    d_null = _deal()
    assert evaluate_filters(_company(), d_null, [], CFG).passes_financial_filter is None
    d_false = _deal(revenue=100_000, revenue_currency="AUD", ebitda=10_000, ebitda_currency="AUD")
    assert evaluate_filters(_company(), d_false, [], CFG).passes_financial_filter is False


def test_founder_filter_true_false_null():
    long_t = [Founder(name="A", role=FounderRole.Founder, start_year=2000, tenure_years=25)]
    assert evaluate_filters(_company(), _deal(), long_t, CFG).passes_founder_filter is True
    short_t = [Founder(name="B", role=FounderRole.Founder, start_year=2022, tenure_years=3)]
    assert evaluate_filters(_company(), _deal(), short_t, CFG).passes_founder_filter is False
    assert evaluate_filters(_company(), _deal(), [], CFG).passes_founder_filter is None


def test_ai_flag_true_false_null():
    d_true = _deal(ai_automation_potential_notes="clear automation upside here")
    assert evaluate_filters(_company(), d_true, [], CFG).ai_automation_potential_flag is True
    d_false = _deal(ai_automation_potential_notes="asset-heavy low-complexity")
    assert evaluate_filters(_company(), d_false, [], CFG).ai_automation_potential_flag is False
    assert evaluate_filters(_company(), _deal(), [], CFG).ai_automation_potential_flag is None


# --- Scoring math ---

def test_all_true_no_penalty_is_90():
    f = FilterResults(True, True, True, True, True)
    assert compute_score(f, 0) == 90


def test_false_and_null_add_nothing():
    f = FilterResults(False, None, False, None, False)
    assert compute_score(f, 0) == 0


def test_penalty_capped_at_20():
    f = FilterResults(True, True, True, True, True)
    assert compute_score(f, 999) == 70  # 90 - 20


def test_clamped_to_zero():
    f = FilterResults(None, None, None, None, None)
    assert compute_score(f, 50) == 0


def test_clamped_to_100():
    # sector+age+financial+founder+ai = 90 max, can't exceed 100 anyway
    f = FilterResults(True, True, True, True, True)
    assert 0 <= compute_score(f, 0) <= 100
