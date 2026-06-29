"""Source-type-specific handlers.

Each handler reads the conventions of its source family and produces a uniform
:class:`RawFields` record plus a list of raw contact dicts. Handlers **never
invent data**: a value is extracted only when it is present in the item's
structured payload or can be safely identified in ``raw_text``. Anything that
cannot be confidently extracted is left as ``None``.

Items carry an optional ``structured`` dict which is the primary, trusted
extraction surface. ``raw_text`` is treated as untrusted free text and is only
mined with conservative keyword heuristics (never for financial figures).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import SourceItem


# A financial value may be a single number or a (low, high) range tuple.
NumberOrRange = Any  # float | tuple[float, float] | None


@dataclass
class RawFields:
    """Uniform intermediate record emitted by every handler."""

    source_name: str = ""
    source_type: str = ""
    external_listing_id_or_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    deal_type: Optional[str] = None
    asking_price: NumberOrRange = None
    asking_price_currency: Optional[str] = None
    revenue: NumberOrRange = None
    revenue_currency: Optional[str] = None
    ebitda: NumberOrRange = None
    ebitda_currency: Optional[str] = None
    listing_date: Optional[str] = None
    last_seen_at: Optional[str] = None
    location_text: Optional[str] = None
    is_franchise: bool = False
    has_deal: bool = True
    company: dict[str, Any] = field(default_factory=dict)
    founders: list[dict[str, Any]] = field(default_factory=list)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    competitive_notes: Optional[str] = None
    ai_automation_notes: Optional[str] = None
    raw_text: str = ""


_FRANCHISE_RE = re.compile(r"\bfranchis", re.IGNORECASE)
_AUTOMATION_RE = re.compile(
    r"\b(manual|spreadsheet|paper[- ]based|repetitive|back[- ]office|"
    r"data entry|bookkeep|invoic|scheduling)\b",
    re.IGNORECASE,
)
_ASSET_HEAVY_RE = re.compile(
    r"\b(asset[- ]heavy|equipment|machinery|fleet|warehouse|plant)\b",
    re.IGNORECASE,
)


def _struct(item: SourceItem) -> dict[str, Any]:
    return item.structured or {}


def _detect_franchise(item: SourceItem, struct: dict[str, Any]) -> bool:
    if "is_franchise" in struct:
        return bool(struct["is_franchise"])
    return bool(_FRANCHISE_RE.search(item.raw_text or ""))


def _external_ref(item: SourceItem, struct: dict[str, Any]) -> Optional[str]:
    return (
        struct.get("external_listing_id_or_url")
        or struct.get("url")
        or struct.get("listing_id")
        or item.external_listing_id_or_url
    )


def _company_from_struct(struct: dict[str, Any]) -> dict[str, Any]:
    """Pull company fields from a structured payload, omitting absent ones."""

    company_src = struct.get("company", struct)
    out: dict[str, Any] = {}
    for key in (
        "name",
        "country",
        "state",
        "city",
        "postcode",
        "sector",
        "subsector",
        "founded_year",
        "employees",
        "notes_about_business_model",
    ):
        if company_src.get(key) is not None:
            out[key] = company_src[key]
    return out


def _automation_notes(item: SourceItem, struct: dict[str, Any]) -> Optional[str]:
    if struct.get("ai_automation_potential_notes"):
        return struct["ai_automation_potential_notes"]
    text = item.raw_text or ""
    if _AUTOMATION_RE.search(text):
        return "Mentions recurring manual / back-office processes with automation upside."
    if _ASSET_HEAVY_RE.search(text):
        return "Appears asset-heavy / low-complexity; limited near-term automation upside."
    return None


def _base_fields(item: SourceItem) -> RawFields:
    struct = _struct(item)
    rf = RawFields(
        source_name=item.source_name,
        source_type=item.source_type,
        external_listing_id_or_url=_external_ref(item, struct),
        title=struct.get("title"),
        description=struct.get("description"),
        listing_date=struct.get("listing_date"),
        last_seen_at=struct.get("last_seen_at"),
        location_text=struct.get("location_text"),
        is_franchise=_detect_franchise(item, struct),
        company=_company_from_struct(struct),
        founders=list(struct.get("founders", []) or []),
        contacts=list(struct.get("contacts", []) or []),
        competitive_notes=struct.get("competitive_notes"),
        ai_automation_notes=_automation_notes(item, struct),
        raw_text=item.raw_text or "",
    )
    return rf


def _copy_financials(rf: RawFields, struct: dict[str, Any]) -> None:
    """Copy financial figures from a trusted structured payload only."""

    if struct.get("asking_price") is not None:
        rf.asking_price = struct["asking_price"]
        rf.asking_price_currency = struct.get("asking_price_currency", "AUD")
    if struct.get("revenue") is not None:
        rf.revenue = struct["revenue"]
        rf.revenue_currency = struct.get("revenue_currency", "AUD")
    if struct.get("ebitda") is not None:
        rf.ebitda = struct["ebitda"]
        rf.ebitda_currency = struct.get("ebitda_currency", "AUD")


# ---------------------------------------------------------------------------
# Per-source-type handlers
# ---------------------------------------------------------------------------


def handle_marketplace(item: SourceItem) -> RawFields:
    """Marketplace listings (incl. scaling.com.au): deal fields + broker contacts."""

    struct = _struct(item)
    rf = _base_fields(item)
    rf.deal_type = "franchise" if rf.is_franchise else struct.get("deal_type", "sale")
    _copy_financials(rf, struct)
    return rf


def handle_broker_directory(item: SourceItem) -> RawFields:
    """Broker directory: primarily a source of contacts; deals are optional."""

    struct = _struct(item)
    rf = _base_fields(item)
    rf.deal_type = struct.get("deal_type", "other")
    _copy_financials(rf, struct)
    # Annotate broker contacts with their sector / deal-size focus when present.
    for c in rf.contacts:
        c.setdefault("role_or_title", "Broker")
    rf.has_deal = bool(struct.get("has_deal", "title" in struct))
    return rf


def handle_insolvency_platform(item: SourceItem) -> RawFields:
    """Insolvency platform: distressed entity + practitioner contacts."""

    struct = _struct(item)
    rf = _base_fields(item)
    rf.deal_type = "distress"
    _copy_financials(rf, struct)
    for c in rf.contacts:
        c.setdefault("role_or_title", "Practitioner")
    return rf


def handle_chamber_directory(item: SourceItem) -> RawFields:
    """Chamber directory: off-market target firm + association-official leads."""

    struct = _struct(item)
    rf = _base_fields(item)
    rf.deal_type = struct.get("deal_type", "other")
    _copy_financials(rf, struct)
    for c in rf.contacts:
        c.setdefault("role_or_title", "Association Official")
    rf.has_deal = bool(struct.get("has_deal", "title" in struct))
    return rf


def handle_social_or_news(item: SourceItem) -> RawFields:
    """Social / news: company + deal signal only. Hype is never financial proof."""

    struct = _struct(item)
    rf = _base_fields(item)
    rf.deal_type = struct.get("deal_type", "other")
    # Deliberately DO NOT copy financial figures from social/news structured
    # payloads: marketing claims are not treated as financial evidence.
    if not rf.title:
        rf.title = (item.raw_text or "").strip().split("\n", 1)[0][:120] or None
    return rf


def handle_generic(item: SourceItem) -> RawFields:
    """Fallback handler for unknown source types: safe fields only, rest null."""

    rf = _base_fields(item)
    rf.deal_type = "other"
    if not rf.title:
        rf.title = (item.raw_text or "").strip().split("\n", 1)[0][:120] or None
    return rf


def extract_contacts(item: SourceItem, rf: RawFields) -> list[dict[str, Any]]:
    """Return the raw contact dicts gathered by the handler for ``item``."""

    return rf.contacts
