"""Hypothesis strategies generating varied batches of source items.

The generators intentionally explore the full input space: mixed source types
(including unknown ones), partial / missing fields, edge financials, banned
sectors, oversized enterprise values, ranges, and stale / unknown dates.
"""

from __future__ import annotations

from hypothesis import strategies as st

from app.config import load_thesis_config

# A pinned config so property runs are reproducible.
FIXED_CONFIG = load_thesis_config({"current_year": 2025, "current_date": "2025-06-01"})

SOURCE_TYPES = [
    "marketplace",
    "broker_directory",
    "insolvency_platform",
    "chamber_directory",
    "social",
    "news",
    "unknown_kind",  # exercises the generic-handler fallback
]

SECTORS = [
    "manufacturing",
    "bookkeeping",
    "engineering services",
    "logistics",
    "retail",
    None,
]

BANNED_SECTORS = ["tobacco", "liquor", "gambling", "casino", "betting"]

SOURCE_NAMES = [
    "scaling.com.au",
    "scalingup.com.au",
    "ASIC Notices",
    "Victorian Chamber",
    "LinkedIn",
    "Industry News",
]

DATES = [
    "2025-05-01",  # fresh
    "2024-12-01",  # fresh-ish
    "2019-01-01",  # stale
    "2015-06-01",  # very stale
    None,          # unknown_date
]


@st.composite
def financial_value(draw):
    """A financial figure: None, a number, or a (low, high) range."""

    kind = draw(st.sampled_from(["none", "number", "range"]))
    if kind == "none":
        return None
    if kind == "number":
        return draw(st.integers(min_value=0, max_value=90_000_000))
    low = draw(st.integers(min_value=0, max_value=40_000_000))
    high = draw(st.integers(min_value=low, max_value=90_000_000))
    return [low, high]


@st.composite
def company_payload(draw):
    sector_choice = draw(st.sampled_from(SECTORS + BANNED_SECTORS))
    payload = {"name": draw(st.sampled_from(["Acme", "Globex", "Initech", "Umbrella"]))}
    if draw(st.booleans()):
        payload["country"] = "Australia"
    if sector_choice is not None:
        payload["sector"] = sector_choice
    founded = draw(st.one_of(st.none(), st.integers(min_value=1950, max_value=2025)))
    if founded is not None:
        payload["founded_year"] = founded
    return payload


@st.composite
def founder_payload(draw):
    f = {"name": draw(st.sampled_from(["Jane", "John", "Sam", "Pat"])), "role": "Founder"}
    sy = draw(st.one_of(st.none(), st.integers(min_value=1970, max_value=2025)))
    if sy is not None:
        f["start_year"] = sy
    if draw(st.booleans()):
        f["email"] = "person@example.com"
    return f


@st.composite
def contact_payload(draw):
    return {
        "person_or_org_name": draw(st.sampled_from(["Broker B", "Liq L", "Banker K", "Official O"])),
        "role_or_title": draw(st.sampled_from(["Broker", "Practitioner", "Banker", "Association Official", None])),
        "email": draw(st.one_of(st.none(), st.just("c@example.com"))),
    }


@st.composite
def source_item(draw):
    stype = draw(st.sampled_from(SOURCE_TYPES))
    structured = {
        "title": draw(st.sampled_from(["Listing A", "Listing B", "Opportunity"])),
        "url": "https://example.com/" + draw(st.sampled_from(["a", "b", "c", "d"])),
        "company": draw(company_payload()),
    }
    rev = draw(financial_value())
    if rev is not None:
        structured["revenue"] = rev
        structured["revenue_currency"] = "AUD"
    eb = draw(financial_value())
    if eb is not None:
        structured["ebitda"] = eb
        structured["ebitda_currency"] = "AUD"
    ap = draw(financial_value())
    if ap is not None:
        structured["asking_price"] = ap
        structured["asking_price_currency"] = "AUD"

    ld = draw(st.sampled_from(DATES))
    if ld is not None:
        structured["listing_date"] = ld
    ls = draw(st.sampled_from(DATES))
    if ls is not None:
        structured["last_seen_at"] = ls

    if draw(st.booleans()):
        structured["founders"] = draw(st.lists(founder_payload(), max_size=3))
    if draw(st.booleans()):
        structured["contacts"] = draw(st.lists(contact_payload(), max_size=3))

    raw_text = draw(
        st.sampled_from(
            [
                "Business for sale with manual bookkeeping processes.",
                "Asset-heavy fleet and warehouse operation.",
                "Franchise opportunity available now.",
                "Great growth story, huge revenue claims!",
                "Regional firm, owner retiring.",
            ]
        )
    )

    return {
        "source_name": draw(st.sampled_from(SOURCE_NAMES)),
        "source_type": stype,
        "raw_text": raw_text,
        "structured": structured,
    }


def batch_strategy(min_size: int = 0, max_size: int = 12):
    return st.lists(source_item(), min_size=min_size, max_size=max_size)
