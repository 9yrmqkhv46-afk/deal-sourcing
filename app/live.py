"""Live-data API service layer.

This module is a thin, ADDITIVE orchestration layer that powers the live GET
endpoints (``/api/brokers/deals``, ``/api/franchises/deals``,
``/api/insolvency/opportunities``, ``/api/linkedin/posts``, ``/api/live/today``).

Principles (must always hold):

* **Never fabricate data.** We only return what live connectors actually
  provide. Nothing is invented or back-filled with sample data here.
* **No sample fallback for LIVE endpoints.** Unlike ``/api/refresh``, these
  endpoints reflect reality: when no source is configured (or a configured
  source returns nothing) they respond with empty lists plus a clear ``note``
  explaining why.
* **Reuse the existing deterministic pipeline.** Fetched
  :class:`~app.models.SourceItem` objects flow through the EXISTING
  ``process_batch`` (ingestion -> route -> ... -> assemble); we never recompute
  scores or duplicate the Apify HTTP logic.
* **LinkedIn stays ToS-compliant and credential-gated** via
  :class:`~app.connectors.linkedin_connector.LinkedInConnector`; no scraping or
  anti-bot logic lives here.

The connector accessors (:func:`_connector_for`, :func:`_linkedin_connector`)
are deliberately small seams so tests can monkeypatch a fake connector that
yields canned :class:`SourceItem` objects with no network access.
"""

from __future__ import annotations

from typing import Any, Optional

from . import store
from .connectors import get_connector
from .connectors.base import Connector
from .connectors.linkedin_connector import LinkedInConnector
from .models import Company, Deal, LinkedInPost, SourceItem, SourceType
from .pipeline import process_batch
from .sources import REGISTRY, resolve_source_key

# --- Source grouping --------------------------------------------------------

#: Source types treated as broker / marketplace style deal listings.
_BROKER_TYPES = {SourceType.marketplace, SourceType.broker_directory}

#: The dedicated franchise source key(s).
_FRANCHISE_KEYS = ("franchise2sell",)

MAX_TOP_DEALS = 20
MAX_TOP_POSTS = 50


def _group_source_keys(group: str) -> list[str]:
    """Return the registry source keys that belong to a deal ``group``.

    * ``"broker"``     -> every marketplace / broker_directory source (the 10 AU
      sites plus scaling / scalingup).
    * ``"franchise"``  -> the dedicated franchise source(s).
    * ``"insolvency"`` -> every ``insolvency_platform`` source (none are
      registered today, so this yields an empty list and the endpoint returns
      empty results plus a note rather than fabricating opportunities).
    """

    if group == "broker":
        return [e.key for e in REGISTRY.all() if e.source_type in _BROKER_TYPES]
    if group == "franchise":
        return [k for k in _FRANCHISE_KEYS if REGISTRY.get(k) is not None]
    if group == "insolvency":
        return [e.key for e in REGISTRY.all() if e.source_type is SourceType.insolvency_platform]
    return []


# --- Connector seams (monkeypatchable in tests) -----------------------------


def _connector_for(source_key: str) -> Connector:
    """Return the connector for a registry source key (test seam)."""

    return get_connector(source_key)


def _linkedin_connector() -> Connector:
    """Return the credential-gated LinkedIn connector (test seam)."""

    return LinkedInConnector()


# --- Notes ------------------------------------------------------------------

_NO_BROKER_NOTE = (
    "No configured live broker/marketplace sources — set APIFY_TOKEN plus an actor "
    "(a per-source APIFY_ACTOR_<SOURCE> or the shared APIFY_DEFAULT_ACTOR) to pull "
    "live listings. No sample data is returned for live endpoints."
)
_NO_FRANCHISE_NOTE = (
    "No configured live franchise source — set APIFY_TOKEN plus APIFY_ACTOR_FRANCHISE2SELL "
    "(or APIFY_DEFAULT_ACTOR). No sample data is returned for live endpoints."
)
_NO_INSOLVENCY_NOTE = (
    "No configured insolvency-platform source — no live insolvency connector is "
    "available, so no opportunities can be returned. No sample data is returned for "
    "live endpoints."
)
_LINKEDIN_NOTE = (
    "LinkedIn is not configured. Live LinkedIn ingestion requires your OWN authorized "
    "source (official API token or an authorized Apify actor) and ToS compliance: set "
    "LINKEDIN_INGEST_ENABLED=true plus LINKEDIN_API_TOKEN (or APIFY_TOKEN + "
    "APIFY_ACTOR_LINKEDIN). No sample data is returned for live endpoints."
)

_NO_SOURCE_NOTE = {
    "broker": _NO_BROKER_NOTE,
    "franchise": _NO_FRANCHISE_NOTE,
    "insolvency": _NO_INSOLVENCY_NOTE,
}


def _empty_returned_note(group: str) -> str:
    return (
        f"Configured live {group} source(s) returned no listings. Only live results are "
        "reported — no sample data is substituted."
    )


# --- Tolerant LinkedIn mapping ----------------------------------------------

_LI_ID_KEYS: tuple[str, ...] = ("id", "postId", "post_id", "urn", "activityId", "activity_id")
_LI_AUTHOR_KEYS: tuple[str, ...] = (
    "author_name", "authorName", "author", "name", "fullName", "full_name", "authorFullName",
)
_LI_AUTHOR_URL_KEYS: tuple[str, ...] = (
    "author_linkedin_url", "authorUrl", "author_url", "authorProfileUrl",
    "profileUrl", "profile_url", "authorLinkedinUrl",
)
_LI_TEXT_KEYS: tuple[str, ...] = (
    "text", "content", "post", "postText", "post_text", "body", "commentary",
)
_LI_CREATED_KEYS: tuple[str, ...] = (
    "created_at", "createdAt", "date", "postedAt", "posted_at", "publishedAt",
    "published_at", "time", "timestamp",
)
_LI_URL_KEYS: tuple[str, ...] = (
    "url", "postUrl", "post_url", "link", "permalink", "href", "detailUrl",
)


def _first(record: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    """Return the first present, non-empty value among ``keys`` as a string."""

    if not isinstance(record, dict):
        return None
    for key in keys:
        if key not in record:
            continue
        value = record.get(key)
        if value is None:
            continue
        text = value if isinstance(value, str) else str(value)
        text = text.strip()
        if text:
            return text
    return None


def map_linkedin_record(record: dict[str, Any], fallback_id: Optional[str] = None) -> LinkedInPost:
    """Map one raw LinkedIn dataset record into a :class:`LinkedInPost` (pure).

    Tolerant like the Apify mapper: it probes a wide set of common field names
    and never fabricates a value it did not find. ``id`` falls back to the post
    URL, then to ``fallback_id`` (so an id is always present), but author/text/
    timestamp stay ``None`` when absent.
    """

    url = _first(record, _LI_URL_KEYS)
    post_id = _first(record, _LI_ID_KEYS) or url or (fallback_id or "")
    return LinkedInPost(
        id=post_id,
        author_name=_first(record, _LI_AUTHOR_KEYS),
        author_linkedin_url=_first(record, _LI_AUTHOR_URL_KEYS),
        text=_first(record, _LI_TEXT_KEYS),
        created_at=_first(record, _LI_CREATED_KEYS),
        url=url,
    )


def linkedin_post_from_source_item(item: SourceItem) -> LinkedInPost:
    """Project a connector :class:`SourceItem` into a :class:`LinkedInPost`.

    The connector carries the original record through ``SourceItem.structured``;
    we map from that when available, then back-fill ``url`` from the item's
    external ref and ``text`` from the raw text blob. Nothing is fabricated.
    """

    structured = item.structured if isinstance(item.structured, dict) else {}
    fallback_id = item.external_listing_id_or_url or None
    post = map_linkedin_record(structured, fallback_id=fallback_id)

    if not post.url and item.external_listing_id_or_url:
        post.url = item.external_listing_id_or_url
    if not post.id:
        post.id = item.external_listing_id_or_url or ""
    if not post.text and item.raw_text:
        post.text = item.raw_text
    return post


# --- Deal projection --------------------------------------------------------


def project_deal(deal: Deal, companies_by_id: dict[str, Company]) -> dict[str, Any]:
    """Project an internal :class:`Deal` into the live "broker deal" shape.

    The output dict has EXACTLY the contract keys::

        id, source_name, source_url, title, sector, location, asking_price,
        revenue, ebitda, listing_date, thesis_match{...}

    ``source_url`` is the deal's already-computed ``listing_url`` (base_url +
    external id). ``sector`` comes from the linked company. No value is
    fabricated — missing inputs stay ``None``.
    """

    company = companies_by_id.get(deal.company_id or "")
    tm = deal.thesis_match
    return {
        "id": deal.deal_id,
        "source_name": deal.source_name,
        "source_url": deal.listing_url,
        "title": deal.title,
        "sector": company.sector if company else None,
        "location": deal.location_text,
        "asking_price": deal.asking_price,
        "revenue": deal.revenue,
        "ebitda": deal.ebitda,
        "listing_date": deal.listing_date,
        "thesis_match": {
            "passes_age_filter": tm.passes_age_filter,
            "passes_sector_filter": tm.passes_sector_filter,
            "passes_financial_filter": tm.passes_financial_filter,
            "passes_founder_filter": tm.passes_founder_filter,
            "ai_automation_potential_flag": tm.ai_automation_potential_flag,
            "overall_score": tm.overall_score,
            "classification": tm.classification.value,
            "explanation": tm.explanation,
        },
    }


def _matches_country(deal: Deal, companies_by_id: dict[str, Company], country: Optional[str]) -> bool:
    """Lenient geography filter: keep AU/unknown, drop confidently-foreign.

    When the linked company has a *known* country we require it to match; when
    the country is unknown we keep the deal (and flag missing data downstream)
    rather than dropping or fabricating a location.
    """

    if not country:
        return True
    target = country.strip().lower()
    company = companies_by_id.get(deal.company_id or "")
    known = (company.country or "").strip().lower() if company else ""
    if known and known != "unknown":
        if known == target:
            return True
        # Fall back to a textual hint before dropping.
        return target in (deal.location_text or "").lower()
    return True


def _deal_summary(deals: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the deal summary: core/adjacent counts + top core ids (<=20)."""

    core = [d for d in deals if d["thesis_match"]["classification"] == "core_thesis"]
    adjacent = [d for d in deals if d["thesis_match"]["classification"] == "adjacent_thesis"]
    core_sorted = sorted(core, key=lambda d: (-d["thesis_match"]["overall_score"], d["id"]))
    return {
        "core_thesis_deal_count": len(core),
        "adjacent_thesis_deal_count": len(adjacent),
        "top_core_thesis_deals": [d["id"] for d in core_sorted][:MAX_TOP_DEALS],
    }


def _empty_deal_summary() -> dict[str, Any]:
    return {
        "core_thesis_deal_count": 0,
        "adjacent_thesis_deal_count": 0,
        "top_core_thesis_deals": [],
    }


# --- Live deal fetch + shaping ----------------------------------------------


_NO_LIVE_SNAPSHOT_NOTE = (
    "No live data yet — add APIFY_TOKEN and run POST /api/sync (or click Sync now)."
)


def _live_snapshot() -> Optional[dict[str, Any]]:
    """Return the latest live-sync snapshot record (test seam)."""

    return store.load_latest_live_snapshot()


def _shape_deals_from_snapshot(
    group: str, snapshot: dict[str, Any], limit: Optional[int], country: Optional[str]
) -> dict[str, Any]:
    """Shape live deals for a ``group`` from a stored live-sync snapshot.

    Deals/companies are rebuilt from the snapshot's strict payload and filtered
    by group: ``broker`` -> marketplace/broker_directory; ``franchise`` ->
    ``is_franchise``; ``insolvency`` -> ``insolvency_platform``. NEVER returns
    sample data.
    """

    companies = [Company(**c) for c in snapshot.get("companies", []) or []]
    companies_by_id = {c.company_id: c for c in companies}
    deals = [Deal(**d) for d in snapshot.get("deals", []) or []]

    if group == "broker":
        deals = [d for d in deals if d.source_type in _BROKER_TYPES]
    elif group == "franchise":
        deals = [d for d in deals if d.is_franchise]
    elif group == "insolvency":
        deals = [d for d in deals if d.source_type is SourceType.insolvency_platform]
    else:
        deals = []

    deals = [d for d in deals if _matches_country(d, companies_by_id, country)]
    projected = [project_deal(d, companies_by_id) for d in deals]
    if limit is not None and limit >= 0:
        projected = projected[:limit]

    note = None if projected else _empty_returned_note(group)
    return {"deals": projected, "summary": _deal_summary(projected), "note": note}


def fetch_live_deals(group: str, limit: Optional[int], country: Optional[str]) -> dict[str, Any]:
    """Fetch live deals for a source ``group`` and shape the response.

    Reads from the latest LIVE-sync snapshot when one exists (the data the
    scheduler / ``POST /api/sync`` produced from the Apify actor registry). When
    no live snapshot exists yet it falls back to fetching directly from any
    configured live connector. In NO case is seeded sample data returned: with
    neither a live snapshot nor a configured source, ``deals`` is empty and
    ``note`` explains why.
    """

    snapshot = _live_snapshot()
    if snapshot is not None:
        result = _shape_deals_from_snapshot(group, snapshot, limit, country)
        return result

    keys = _group_source_keys(group)
    configured = [k for k in keys if _safe_is_configured(k)]

    if not configured:
        note = _NO_SOURCE_NOTE.get(group, "") or _NO_LIVE_SNAPSHOT_NOTE
        return {"deals": [], "summary": _empty_deal_summary(), "note": note}

    items: list[SourceItem] = []
    for key in configured:
        try:
            items.extend(_connector_for(key).fetch() or [])
        except Exception:  # a connector must never crash the endpoint
            continue

    if not items:
        return {"deals": [], "summary": _empty_deal_summary(), "note": _empty_returned_note(group)}

    output = process_batch(items)
    companies_by_id = {c.company_id: c for c in output.companies}

    deals = list(output.deals)
    if group == "franchise":
        deals = [
            d for d in deals
            if d.is_franchise or resolve_source_key(d.source_name) in _FRANCHISE_KEYS
        ]

    deals = [d for d in deals if _matches_country(d, companies_by_id, country)]
    projected = [project_deal(d, companies_by_id) for d in deals]
    if limit is not None and limit >= 0:
        projected = projected[:limit]

    note = None
    if not projected:
        note = _empty_returned_note(group)
    return {"deals": projected, "summary": _deal_summary(projected), "note": note}


def _safe_is_configured(source_key: str) -> bool:
    try:
        return bool(_connector_for(source_key).is_configured())
    except Exception:  # pragma: no cover - defensive
        return False


# --- Public endpoint services -----------------------------------------------


def brokers_deals(limit: int = 50, country: str = "Australia") -> dict[str, Any]:
    """Live broker / marketplace deals."""

    return fetch_live_deals("broker", limit=limit, country=country)


def franchises_deals(limit: int = 50, country: str = "Australia") -> dict[str, Any]:
    """Live franchise deals."""

    return fetch_live_deals("franchise", limit=limit, country=country)


def insolvency_opportunities(country: str = "Australia") -> dict[str, Any]:
    """Live insolvency / distress opportunities."""

    return fetch_live_deals("insolvency", limit=None, country=country)


def linkedin_posts(country: str = "Australia", since_days: int = 1) -> dict[str, Any]:
    """Live LinkedIn posts.

    Prefers the LinkedIn posts attached to the latest LIVE-sync snapshot (what
    the Apify LinkedIn actors produced). When no live snapshot exists, falls
    back to the credential-gated connector. Never returns sample data: with no
    live snapshot and no configured connector, ``linkedin_posts`` is empty and
    ``note`` explains why.

    Returns ``{linkedin_posts, summary{top_linkedin_posts}, note}``.
    """

    snapshot = _live_snapshot()
    if snapshot is not None:
        posts = [p for p in (snapshot.get("linkedin_posts") or []) if isinstance(p, dict)]
        if not posts:
            return {
                "linkedin_posts": [],
                "summary": {"top_linkedin_posts": []},
                "note": "Live sync ran but no LinkedIn posts were returned.",
            }
        top = [p["id"] for p in posts if p.get("id")][:MAX_TOP_POSTS]
        return {"linkedin_posts": posts, "summary": {"top_linkedin_posts": top}, "note": None}

    conn = _linkedin_connector()
    if not _safe_connector_configured(conn):
        return {"linkedin_posts": [], "summary": {"top_linkedin_posts": []}, "note": _LINKEDIN_NOTE}

    try:
        items = conn.fetch() or []
    except Exception:  # never crash the endpoint
        items = []

    posts = [linkedin_post_from_source_item(it).model_dump() for it in items]
    if not posts:
        return {
            "linkedin_posts": [],
            "summary": {"top_linkedin_posts": []},
            "note": "LinkedIn source configured but returned no posts.",
        }

    top = [p["id"] for p in posts if p.get("id")][:MAX_TOP_POSTS]
    return {"linkedin_posts": posts, "summary": {"top_linkedin_posts": top}, "note": None}


def _safe_connector_configured(conn: Connector) -> bool:
    try:
        return bool(conn.is_configured())
    except Exception:  # pragma: no cover - defensive
        return False


def live_today(country: str = "Australia") -> dict[str, Any]:
    """Aggregated "today" view: brokers + franchises (limit 50) + linkedin (1d).

    Merges deals and LinkedIn posts, caps the top lists, and merges per-source
    notes. Reflects only live data; empty + note when nothing is configured.
    """

    brokers = brokers_deals(limit=50, country=country)
    franchises = franchises_deals(limit=50, country=country)
    li = linkedin_posts(country=country, since_days=1)

    # Merge deals, de-duplicating by id (broker group can include franchises).
    merged: dict[str, dict[str, Any]] = {}
    for d in [*brokers["deals"], *franchises["deals"]]:
        merged.setdefault(d["id"], d)
    deals = list(merged.values())
    posts = li["linkedin_posts"]

    core = [d for d in deals if d["thesis_match"]["classification"] == "core_thesis"]
    adjacent = [d for d in deals if d["thesis_match"]["classification"] == "adjacent_thesis"]
    core_sorted = sorted(core, key=lambda d: (-d["thesis_match"]["overall_score"], d["id"]))

    summary = {
        "core_thesis_deal_count": len(core),
        "adjacent_thesis_deal_count": len(adjacent),
        "top_core_thesis_deals": [d["id"] for d in core_sorted][:MAX_TOP_DEALS],
        "top_linkedin_posts": [p["id"] for p in posts if p.get("id")][:MAX_TOP_POSTS],
    }

    notes = [n for n in (brokers.get("note"), franchises.get("note"), li.get("note")) if n]
    note = " | ".join(notes) if notes else None
    return {"deals": deals, "linkedin_posts": posts, "summary": summary, "note": note}
