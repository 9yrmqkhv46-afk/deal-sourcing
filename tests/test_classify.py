"""Task 7.5 - classification boundaries."""

from app.config import load_thesis_config
from app.models import Classification, Company, Deal, SourceType
from app.scoring import FilterResults, build_thesis_match, classify

CFG = load_thesis_config({"current_year": 2025, "current_date": "2025-06-01"})


def _deal(**over):
    base = dict(
        source_name="s",
        source_type=SourceType.marketplace,
        external_listing_id_or_url="u",
        title="t",
    )
    base.update(over)
    return Deal(**base)


def _strong_filters():
    return FilterResults(True, True, True, True, True)


def test_score_below_40_rejects():
    f = FilterResults(True, None, None, None, None)  # 20
    assert classify(20, f, _deal(), CFG) is Classification.reject


def test_score_39_rejects_40_adjacent():
    f = _strong_filters()
    assert classify(39, f, _deal(), CFG) is Classification.reject
    assert classify(40, f, _deal(), CFG) is Classification.adjacent_thesis


def test_score_69_adjacent_70_core():
    f = _strong_filters()
    assert classify(69, f, _deal(), CFG) is Classification.adjacent_thesis
    assert classify(70, f, _deal(), CFG) is Classification.core_thesis


def test_banned_sector_always_reject_even_high_score():
    f = FilterResults(True, False, True, True, True)
    assert classify(95, f, _deal(), CFG) is Classification.reject


def test_oversized_always_reject_even_high_score():
    f = _strong_filters()
    big = _deal(asking_price=80_000_000, asking_price_currency="AUD")
    assert classify(95, f, big, CFG) is Classification.reject


def test_one_key_unknown_others_strong_is_adjacent():
    # score 65 (sector+age+financial+ai = 75 minus penalty path) lands 40-69
    f = FilterResults(True, True, True, None, True)
    assert classify(65, f, _deal(), CFG) is Classification.adjacent_thesis


def test_explanation_cites_filters():
    f = _strong_filters()
    company = Company(name="Co", country="Australia")
    tm = build_thesis_match(f, 85, Classification.core_thesis, _deal(), company, CFG)
    assert "Filters" in tm.explanation
    assert "Core thesis" in tm.explanation
