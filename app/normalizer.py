"""Normalizer & Inference Engine.

Converts :class:`RawFields` into typed entity fields, performing conservative
inference: ranges become midpoints flagged ``ESTIMATED``; derived fields
(``age_years``, ``tenure_years``) are computed only when source data supports
them; everything else nulls out. No marketing hype is treated as financial
evidence (handlers already withhold social/news figures).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from .config import ThesisConfig
from .handlers import RawFields
from .models import (
    Company,
    Deal,
    DealSizeBucket,
    DealType,
    Founder,
    FounderRole,
    SourceType,
    UNKNOWN_DATE,
)


def _is_range(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2


def _resolve_number(value: Any) -> tuple[Optional[float], bool]:
    """Return ``(number, estimated)`` for a value that may be a range.

    A range is reduced to its midpoint and flagged estimated. A plain number is
    returned as-is. Anything else yields ``(None, False)``.
    """

    if value is None:
        return None, False
    if _is_range(value):
        low, high = float(value[0]), float(value[1])
        return (low + high) / 2.0, True
    try:
        return float(value), False
    except (TypeError, ValueError):
        return None, False


def _is_banned_sector(sector: Optional[str], notes: Optional[str], config: ThesisConfig) -> bool:
    haystack = " ".join(filter(None, [sector or "", notes or ""])).lower()
    if not haystack:
        return False
    return any(banned in haystack for banned in config.banned_sectors)


def normalize_company(rf: RawFields, config: ThesisConfig) -> Company:
    """Build a :class:`Company` from RawFields, nulling unverifiable fields."""

    src = rf.company or {}
    name = src.get("name") or _fallback_company_name(rf)
    country = src.get("country") or _infer_country(rf, config)

    founded_year = src.get("founded_year")
    age_years = None
    if isinstance(founded_year, int):
        age_years = config.current_year - founded_year

    sector = src.get("sector")
    notes = src.get("notes_about_business_model")
    banned = _is_banned_sector(sector, notes, config) or _is_banned_sector(
        rf.title, rf.raw_text, config
    )

    return Company(
        name=name,
        country=country,
        state=src.get("state"),
        city=src.get("city"),
        postcode=src.get("postcode"),
        sector=sector,
        subsector=src.get("subsector"),
        founded_year=founded_year if isinstance(founded_year, int) else None,
        age_years=age_years,
        employees=src.get("employees") if isinstance(src.get("employees"), int) else None,
        banned_sector_flag=banned,
        notes_about_business_model=notes,
    )


def _fallback_company_name(rf: RawFields) -> str:
    if rf.title:
        return rf.title.strip()[:120]
    return "unknown"


def _infer_country(rf: RawFields, config: ThesisConfig) -> str:
    text = " ".join(filter(None, [rf.location_text, rf.raw_text])).lower()
    au_markers = (
        "australia",
        " nsw",
        " vic",
        " qld",
        " wa",
        " sa",
        " tas",
        " act",
        " nt",
        "sydney",
        "melbourne",
        "brisbane",
        "perth",
        "adelaide",
    )
    if any(marker in text for marker in au_markers):
        return config.primary_geography
    return "unknown"


def best_estimate_ev(deal: Deal) -> Optional[float]:
    """Best-estimate enterprise value from asking price (preferred) or EBITDA."""

    if deal.asking_price is not None:
        return deal.asking_price
    # Conservative EBITDA multiple proxy when only earnings are known.
    if deal.ebitda is not None:
        return deal.ebitda * 5.0
    return None


def infer_deal_size_bucket(deal: Deal, config: ThesisConfig) -> DealSizeBucket:
    """Map an enterprise value to a size bucket; ``unknown`` when no EV."""

    ev = best_estimate_ev(deal)
    if ev is None:
        return DealSizeBucket.unknown
    if ev > config.ev_absolute_max:
        return DealSizeBucket.upper_mid
    if config.ev_core_min <= ev <= config.ev_core_max:
        return DealSizeBucket.core_mid
    if ev > config.ev_core_max:
        return DealSizeBucket.upper_mid
    # Below the core minimum: split small vs lower_mid by magnitude.
    if ev < config.ev_core_min * 0.2:
        return DealSizeBucket.small
    return DealSizeBucket.lower_mid


def _parse_date(value: Optional[str]) -> Optional[_dt.date]:
    if not value or value == UNKNOWN_DATE:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return _dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def infer_recency(rf: RawFields, config: ThesisConfig) -> tuple[str, str, bool]:
    """Return ``(listing_date, last_seen_at, is_stale)``.

    Missing both dates -> both ``"unknown_date"`` and ``is_stale=False``. A most
    recent date older than ``recency_cutoff_months`` -> ``is_stale=True``.
    """

    listing = rf.listing_date
    last_seen = rf.last_seen_at

    if not listing and not last_seen:
        return UNKNOWN_DATE, UNKNOWN_DATE, False

    parsed = [d for d in (_parse_date(listing), _parse_date(last_seen)) if d is not None]
    listing_out = listing or UNKNOWN_DATE
    last_seen_out = last_seen or UNKNOWN_DATE

    if not parsed:
        return listing_out, last_seen_out, False

    reference = max(parsed)
    today = _parse_date(config.current_date) or _dt.date.today()
    months = (today.year - reference.year) * 12 + (today.month - reference.month)
    is_stale = months > config.recency_cutoff_months
    return listing_out, last_seen_out, is_stale


def normalize_deal(rf: RawFields, company: Company, config: ThesisConfig) -> Deal:
    """Build a :class:`Deal` from RawFields with conservative inference."""

    revenue, revenue_est = _resolve_number(rf.revenue)
    ebitda, ebitda_est = _resolve_number(rf.ebitda)
    asking, asking_est = _resolve_number(rf.asking_price)

    try:
        deal_type = DealType(rf.deal_type) if rf.deal_type else DealType.other
    except ValueError:
        deal_type = DealType.other
    if rf.is_franchise:
        deal_type = DealType.franchise

    listing_date, last_seen_at, is_stale = infer_recency(rf, config)

    external = rf.external_listing_id_or_url or f"{rf.source_name}:{(rf.title or 'item')[:60]}"
    title = rf.title or "unknown"

    competitive = rf.competitive_notes
    if rf.is_franchise and not competitive:
        competitive = "Franchise operator; capture unit-economics and moat vs large brands."

    deal = Deal(
        source_name=rf.source_name,
        source_type=SourceType(rf.source_type),
        external_listing_id_or_url=external,
        title=title,
        description=rf.description,
        deal_type=deal_type,
        asking_price=asking,
        asking_price_currency=rf.asking_price_currency or ("AUD" if asking is not None else None),
        asking_price_estimated=asking_est,
        revenue=revenue,
        revenue_currency=rf.revenue_currency or ("AUD" if revenue is not None else None),
        revenue_estimated=revenue_est,
        ebitda=ebitda,
        ebitda_currency=rf.ebitda_currency or ("AUD" if ebitda is not None else None),
        ebitda_estimated=ebitda_est,
        listing_date=listing_date,
        last_seen_at=last_seen_at,
        location_text=rf.location_text,
        is_franchise=rf.is_franchise,
        competitive_notes=competitive,
        ai_automation_potential_notes=rf.ai_automation_notes,
        raw_source_excerpt=(rf.raw_text or "")[:500],
        is_stale=is_stale,
    )
    deal.deal_size_bucket = infer_deal_size_bucket(deal, config)
    return deal


_ROLE_MAP = {role.value.lower(): role for role in FounderRole}


def normalize_founders(rf: RawFields, config: ThesisConfig) -> list[Founder]:
    """Build :class:`Founder` records, deriving tenure only from start_year."""

    out: list[Founder] = []
    for src in rf.founders:
        name = src.get("name")
        if not name:
            continue
        role_raw = (src.get("role") or "Founder").strip()
        role = _ROLE_MAP.get(role_raw.lower(), FounderRole.Founder)
        start_year = src.get("start_year")
        tenure = None
        if isinstance(start_year, int):
            tenure = config.current_year - start_year
        out.append(
            Founder(
                name=name,
                role=role,
                start_year=start_year if isinstance(start_year, int) else None,
                tenure_years=tenure,
                linkedin_url=src.get("linkedin_url"),
                email=src.get("email"),
                phone=src.get("phone"),
                organization_name=src.get("organization_name") or (rf.company or {}).get("name"),
            )
        )
    return out
