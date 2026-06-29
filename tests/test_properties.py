"""Property-based tests for correctness invariants P1-P17.

Feature: deal-sourcing-agent
Each test runs a minimum of 100 generated batches.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models import Classification
from app.normalizer import best_estimate_ev
from app.pipeline import process_batch
from app.scoring import FilterResults, compute_score
from app.validator import REQUIRED_TOP_LEVEL_KEYS, is_strict_valid_json
from tests.strategies import FIXED_CONFIG, batch_strategy

SETTINGS = settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


def _company_of(out, deal):
    for c in out.companies:
        if c.company_id == deal.company_id:
            return c
    return None


# --- P1 / P13 ---------------------------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p1_score_range_and_p13_tristate(batch):
    """Property P1: 0 <= overall_score <= 100; Property P13: filters tri-state."""
    out = process_batch(batch, FIXED_CONFIG)
    for d in out.deals:
        assert 0 <= d.thesis_match.overall_score <= 100
        tm = d.thesis_match
        for val in (
            tm.passes_age_filter,
            tm.passes_sector_filter,
            tm.passes_financial_filter,
            tm.passes_founder_filter,
            tm.ai_automation_potential_flag,
        ):
            assert val in (True, False, None)


# --- P2 / P3 / P4 -----------------------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p2_banned_sector_rejected(batch):
    """Property P2: banned_sector -> reject."""
    out = process_batch(batch, FIXED_CONFIG)
    for d in out.deals:
        company = _company_of(out, d)
        if company and company.banned_sector_flag:
            assert d.thesis_match.classification is Classification.reject


@SETTINGS
@given(batch_strategy())
def test_p3_oversized_rejected(batch):
    """Property P3: oversized (EV > absolute max) -> reject."""
    out = process_batch(batch, FIXED_CONFIG)
    for d in out.deals:
        ev = best_estimate_ev(d)
        if ev is not None and ev > FIXED_CONFIG.ev_absolute_max:
            assert d.thesis_match.classification is Classification.reject


@SETTINGS
@given(batch_strategy())
def test_p4_low_score_rejected(batch):
    """Property P4: score < 40 -> reject."""
    out = process_batch(batch, FIXED_CONFIG)
    for d in out.deals:
        if d.thesis_match.overall_score < 40:
            assert d.thesis_match.classification is Classification.reject


# --- P5 ---------------------------------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p5_core_thesis_floor(batch):
    """Property P5: core_thesis -> score >= 70 AND no exclusion flag."""
    out = process_batch(batch, FIXED_CONFIG)
    for d in out.deals:
        if d.thesis_match.classification is Classification.core_thesis:
            assert d.thesis_match.overall_score >= 70
            assert d.thesis_match.passes_sector_filter is not False
            ev = best_estimate_ev(d)
            assert ev is None or ev <= FIXED_CONFIG.ev_absolute_max


# --- P6 / P7 ----------------------------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p6_provenance_present(batch):
    """Property P6: deals & contacts carry required provenance."""
    out = process_batch(batch, FIXED_CONFIG)
    for d in out.deals:
        assert d.source_name is not None and d.source_name != ""
        assert d.external_listing_id_or_url is not None and d.external_listing_id_or_url != ""
    for c in out.contacts:
        assert c.source_name is not None and c.source_name != ""
        assert c.source_type is not None


@SETTINGS
@given(batch_strategy())
def test_p7_ids_distinct(batch):
    """Property P7: all IDs distinct within the batch."""
    out = process_batch(batch, FIXED_CONFIG)
    for getter in (
        [d.deal_id for d in out.deals],
        [c.company_id for c in out.companies],
        [f.person_id for f in out.founders],
        [c.contact_id for c in out.contacts],
    ):
        assert len(getter) == len(set(getter))


# --- P8 / P9 / P10 / P11 / P16 ---------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p8_p9_p16_top_deals(batch):
    """Property P8/P16: top deals <=20, non-stale, core only; P9: score-desc."""
    out = process_batch(batch, FIXED_CONFIG)
    top = out.summary.top_core_thesis_deals
    assert len(top) <= 20
    for d in top:
        assert d.is_stale is False
        assert d.thesis_match.classification is Classification.core_thesis
    scores = [d.thesis_match.overall_score for d in top]
    assert scores == sorted(scores, reverse=True)
    # P16: no stale deal appears in top list
    top_ids = {d.deal_id for d in top}
    for d in out.deals:
        if d.is_stale:
            assert d.deal_id not in top_ids


@SETTINGS
@given(batch_strategy())
def test_p10_top_contacts(batch):
    """Property P10: top contacts <=50, each with priority_reason."""
    out = process_batch(batch, FIXED_CONFIG)
    top = out.summary.top_contacts_for_outreach
    assert len(top) <= 50
    for c in top:
        assert c.priority_reason is not None


@SETTINGS
@given(batch_strategy())
def test_p11_summary_partitions(batch):
    """Property P11: counts partition the deals."""
    out = process_batch(batch, FIXED_CONFIG)
    s = out.summary
    assert s.core_thesis_deal_count + s.adjacent_thesis_deal_count + s.reject_count == len(out.deals)


# --- P12 --------------------------------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p12_range_derived_flagged_estimated(batch):
    """Property P12: range-derived financial values are flagged ESTIMATED."""
    out = process_batch(batch, FIXED_CONFIG)
    for src, d in zip(_align_sources(batch, out), out.deals):
        if src is None:
            continue
        struct = src.get("structured", {})
        # social/news (and unknown) handlers do not carry financials at all.
        if d.source_type.value in ("social", "news"):
            continue
        for field in ("revenue", "ebitda", "asking_price"):
            raw = struct.get(field)
            if isinstance(raw, list):  # was a range
                assert getattr(d, f"{field}_estimated") is True


def _align_sources(batch, out):
    """Best-effort align deals back to their source dicts by (name, url)."""
    by_key = {}
    for item in batch:
        struct = item.get("structured", {})
        key = (item["source_name"], struct.get("url"))
        by_key.setdefault(key, item)
    aligned = []
    for d in out.deals:
        aligned.append(by_key.get((d.source_name, d.external_listing_id_or_url)))
    return aligned


# --- P14 --------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    st.lists(st.sampled_from([True, False, None]), min_size=5, max_size=5),
    st.lists(st.sampled_from([True, False, None]), min_size=5, max_size=5),
    st.integers(min_value=0, max_value=20),
)
def test_p14_score_monotonic(f1_vals, f2_vals, penalty):
    """Property P14: more true-flags (penalty fixed) never decreases the score."""
    # Make f2 dominate f1: wherever f1 is True, f2 must be True too.
    f2_vals = [
        True if f1_vals[i] is True else f2_vals[i] for i in range(5)
    ]
    f1 = FilterResults(*f1_vals)
    f2 = FilterResults(*f2_vals)
    assert compute_score(f2, penalty) >= compute_score(f1, penalty)


# --- P15 --------------------------------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p15_determinism(batch):
    """Property P15: identical input -> identical output."""
    a = process_batch(batch, FIXED_CONFIG)
    b = process_batch(batch, FIXED_CONFIG)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


# --- P17 --------------------------------------------------------------------

@SETTINGS
@given(batch_strategy())
def test_p17_strict_json_exact_keys(batch):
    """Property P17: output is strict valid JSON with exact top-level keys."""
    out = process_batch(batch, FIXED_CONFIG)
    assert is_strict_valid_json(out)
    assert set(out.model_dump(mode="json").keys()) == REQUIRED_TOP_LEVEL_KEYS
