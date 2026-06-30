"""Apify ACTOR REGISTRY: the catalogue of live deal-sourcing actors.

This module enumerates the 22 Apify actors the deal-sourcing agent runs to pull
LIVE data. One shared ``APIFY_TOKEN`` drives every actor; each actor has a fixed
``actor_id`` (Apify ``~`` form), a default ``input`` payload, and a
``source_type`` that maps it into the existing deterministic pipeline.

The registry is **pure metadata**. No network access happens here. The
connector layer (:mod:`app.connectors.apify_connector`) and the live-sync
routine (:mod:`app.scheduler`) consume it.

Per-actor input overrides are supported via the environment: set
``APIFY_ACTOR_INPUT_<SOURCE_KEY>`` (upper-cased source key) to a JSON object and
it replaces the default ``input`` for that actor. This lets an operator retune
an actor's query without a code change.

Categories -> ``source_type`` mapping:

* CATEGORY 1 "AU/Global Business For Sale" -> ``marketplace``
* CATEGORY 2 "BizBuySell"                  -> ``marketplace``
* CATEGORY 3 "AU Directories"              -> ``broker_directory`` (ASIC ->
  ``chamber_directory``)
* CATEGORY 4 "LinkedIn posts"              -> ``social`` (``is_linkedin=True``)
* CATEGORY 5 "M&A intelligence"            -> ``news``
* CATEGORY 6 "News"                        -> ``news``
* CATEGORY 7 "Deal Marketplaces (extra)"   -> ``marketplace``
* CATEGORY 8 "Company Registries"          -> ``chamber_directory``
* CATEGORY 9 "Local Discovery (Google Maps)" -> ``broker_directory``
* CATEGORY 10 "Social & Search Signals"    -> ``social``/``news``

COMPLIANCE NOTE: This registry intentionally EXCLUDES bulk LinkedIn
personal-profile / company-employee / people-enumeration scrapers (e.g.
``*-profile-scraper``, ``*-company-employees``, ``*-people-scraper``,
``*-employees-bulk``). Those harvest individuals' personal data at scale and are
out of policy. Only public LinkedIn POST-search actors are kept (the four
``harvestapi``/``datadoping`` post actors). The X/Twitter actor is a social
deal-signal source (``is_linkedin=False``) and is NOT a LinkedIn people scraper.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .models import SourceType
from .sources import SourceEntry

logger = logging.getLogger("app.actors")


# --- Category labels --------------------------------------------------------

CATEGORY_AU_GLOBAL_BFS = "AU/Global Business For Sale"
CATEGORY_BIZBUYSELL = "BizBuySell"
CATEGORY_AU_DIRECTORIES = "AU Directories"
CATEGORY_LINKEDIN = "LinkedIn posts"
CATEGORY_MA_INTEL = "M&A intelligence"
CATEGORY_NEWS = "News"
CATEGORY_DEAL_MARKETPLACES_EXTRA = "Deal Marketplaces (extra)"
CATEGORY_COMPANY_REGISTRIES = "Company Registries"
CATEGORY_LOCAL_DISCOVERY = "Local Discovery (Google Maps)"
CATEGORY_SOCIAL_SEARCH = "Social & Search Signals"

#: Stable, ordered list of categories (used by the dashboard grouping).
CATEGORY_ORDER: tuple[str, ...] = (
    CATEGORY_AU_GLOBAL_BFS,
    CATEGORY_BIZBUYSELL,
    CATEGORY_AU_DIRECTORIES,
    CATEGORY_LINKEDIN,
    CATEGORY_MA_INTEL,
    CATEGORY_NEWS,
    CATEGORY_DEAL_MARKETPLACES_EXTRA,
    CATEGORY_COMPANY_REGISTRIES,
    CATEGORY_LOCAL_DISCOVERY,
    CATEGORY_SOCIAL_SEARCH,
)


def _slug(name: str) -> str:
    """Slugify an actor name into a stable lower-snake source key."""

    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


@dataclass
class ActorEntry:
    """One Apify actor in the registry."""

    name: str
    actor_id: str
    source_type: SourceType
    category: str
    input: dict[str, Any] = field(default_factory=dict)
    is_linkedin: bool = False
    source_key: str = ""

    def __post_init__(self) -> None:
        if not self.source_key:
            self.source_key = _slug(self.name)

    def source_entry(self) -> SourceEntry:
        """Build a :class:`SourceEntry` so the tolerant Apify mapper can run.

        ``base_url`` is empty: actor records carry their own absolute URLs, and
        when they do not we never fabricate a domain.
        """

        return SourceEntry(
            key=self.source_key,
            display_name=self.name,
            source_type=self.source_type,
            base_url="",
            apify_actor_env=None,
        )


def _e(
    name: str,
    actor_id: str,
    source_type: SourceType,
    category: str,
    input: dict[str, Any],
    is_linkedin: bool = False,
) -> ActorEntry:
    return ActorEntry(
        name=name,
        actor_id=actor_id,
        source_type=source_type,
        category=category,
        input=input,
        is_linkedin=is_linkedin,
    )


# The canonical actor registry. One APIFY_TOKEN drives all of them.
ACTOR_REGISTRY: list[ActorEntry] = [
    # ===================================================================
    # CATEGORY 1 - AU/Global Business For Sale -> marketplace
    # ===================================================================
    _e(
        "Australia Business For Sale",
        "mai_amm~australia-business-for-sale-scraper",
        SourceType.marketplace,
        CATEGORY_AU_GLOBAL_BFS,
        {"maxItems": 200, "location": "Australia"},
    ),
    _e(
        "BusinessesForSale (solidcode)",
        "solidcode~businesses-for-sale-scraper",
        SourceType.marketplace,
        CATEGORY_AU_GLOBAL_BFS,
        {"country": "Australia", "maxResults": 200, "minCashFlow": 250000},
    ),
    _e(
        "BusinessesForSale (memo23)",
        "memo23~businessesforsale-scraper",
        SourceType.marketplace,
        CATEGORY_AU_GLOBAL_BFS,
        {"maxItems": 200},
    ),
    _e(
        "BusinessesForSale (fatihtahta)",
        "fatihtahta~businessesforsale-scraper",
        SourceType.marketplace,
        CATEGORY_AU_GLOBAL_BFS,
        {"maxResults": 200, "minCashFlow": 250000},
    ),
    _e(
        "BusinessesForSale (getascraper)",
        "getascraper~businessesforsale-scraper",
        SourceType.marketplace,
        CATEGORY_AU_GLOBAL_BFS,
        {"maxItems": 200},
    ),
    # ===================================================================
    # CATEGORY 2 - BizBuySell -> marketplace
    # ===================================================================
    _e(
        "BizBuySell (scrapesage)",
        "scrapesage~bizbuysell-scraper",
        SourceType.marketplace,
        CATEGORY_BIZBUYSELL,
        {
            "keyword": "Australia",
            "minAskingPrice": 500000,
            "maxAskingPrice": 50000000,
            "minCashFlow": 250000,
            "includeDetails": True,
            "maxItems": 100,
        },
    ),
    _e(
        "BizBuySell (fatihtahta)",
        "fatihtahta~bizbuysell-scraper",
        SourceType.marketplace,
        CATEGORY_BIZBUYSELL,
        {
            "useQueryBuilder": True,
            "minAskingPrice": 500000,
            "maxAskingPrice": 50000000,
            "minCashflow": 250000,
            "enrich_data": True,
            "limit": 100,
        },
    ),
    _e(
        "BizBuySell (abotapi)",
        "abotapi~bizbuysell-scraper",
        SourceType.marketplace,
        CATEGORY_BIZBUYSELL,
        {
            "mode": "search",
            "keyword": "manufacturing Australia",
            "minAskingPrice": 500000,
            "maxAskingPrice": 50000000,
            "fetchDetails": True,
            "maxListings": 100,
        },
    ),
    _e(
        "BizBuySell (crawlerbros)",
        "crawlerbros~bizbuysell-scraper",
        SourceType.marketplace,
        CATEGORY_BIZBUYSELL,
        {
            "searchUrl": "https://www.bizbuysell.com/businesses-for-sale/?q=Australia",
            "maxItems": 100,
            "enrichDetails": True,
        },
    ),
    # ===================================================================
    # CATEGORY 3 - AU Directories -> broker_directory (ASIC -> chamber)
    # ===================================================================
    _e(
        "Australia Business Directory (proscraper)",
        "proscraper~australia-business-scraper",
        SourceType.broker_directory,
        CATEGORY_AU_DIRECTORIES,
        {"location": "Sydney", "keyword": "business broker", "maxItems": 200},
    ),
    _e(
        "Yellow Pages AU (datafoundry)",
        "datafoundry~ypau",
        SourceType.broker_directory,
        CATEGORY_AU_DIRECTORIES,
        {"search": "business broker", "location": "Australia", "maxItems": 200},
    ),
    _e(
        "Australia ASIC (parseforge)",
        "parseforge~australia-asic-scraper",
        SourceType.chamber_directory,
        CATEGORY_AU_DIRECTORIES,
        {"searchQuery": "accounting firm", "maxItems": 200},
    ),
    # ===================================================================
    # CATEGORY 4 - LinkedIn posts -> social, is_linkedin=True
    # ===================================================================
    _e(
        "LinkedIn Post Search",
        "harvestapi~linkedin-post-search",
        SourceType.social,
        CATEGORY_LINKEDIN,
        {
            "searchQueries": [
                "business for sale Australia",
                "franchise for sale Australia",
                "acquisition deal Australia",
                "SME sale manufacturing Australia",
                "accounting firm sale Australia",
                "commercial property deal Australia",
            ],
            "maxPosts": 100,
            "postedLimit": "past-week",
            "sortBy": "date",
        },
        is_linkedin=True,
    ),
    _e(
        "LinkedIn Profile Posts",
        "harvestapi~linkedin-profile-posts",
        SourceType.social,
        CATEGORY_LINKEDIN,
        {"targetUrls": [], "maxPosts": 50, "postedLimit": "past-month"},
        is_linkedin=True,
    ),
    _e(
        "LinkedIn Company Posts",
        "harvestapi~linkedin-company-posts",
        SourceType.social,
        CATEGORY_LINKEDIN,
        {"targetUrls": [], "maxPosts": 50, "postedLimit": "past-month"},
        is_linkedin=True,
    ),
    _e(
        "LinkedIn Posts Search (datadoping)",
        "datadoping~linkedin-posts-search-scraper",
        SourceType.social,
        CATEGORY_LINKEDIN,
        {
            "keywords": [
                "business sale Australia",
                "M&A deal Australia",
                "franchise opportunity",
            ],
            "max_posts": 100,
            "sort_by": "date",
            "date_filter": "past-week",
        },
        is_linkedin=True,
    ),
    # ===================================================================
    # CATEGORY 5 - M&A intelligence -> news
    # ===================================================================
    _e(
        "Company Acquisitions M&A",
        "datahyena~company-acquisitions-ma",
        SourceType.news,
        CATEGORY_MA_INTEL,
        {"maxItems": 100},
    ),
    _e(
        "Owler Intelligence",
        "foxlabs~owler-intelligence",
        SourceType.news,
        CATEGORY_MA_INTEL,
        {
            "companyNames": [],
            "includeAcquisitions": True,
            "includeFunding": True,
            "includeNewsEvents": True,
            "maxResults": 50,
        },
    ),
    _e(
        "Funding Press Signal Scanner",
        "mambalabs~funding-press-signal-scanner",
        SourceType.news,
        CATEGORY_MA_INTEL,
        {"maxItems": 100},
    ),
    # ===================================================================
    # CATEGORY 6 - News -> news
    # ===================================================================
    _e(
        "Google News",
        "nexgendata~google-news-scraper",
        SourceType.news,
        CATEGORY_NEWS,
        {
            "queries": [
                "business acquisition Australia SME",
                "manufacturing company sale Australia",
                "franchise acquisition Australia",
                "accounting firm acquisition Australia",
                "private equity deal Australia 2026",
            ],
            "country": "AU",
            "maxArticles": 50,
            "publishedAfter": "2025-06-01",
        },
    ),
    _e(
        "Crunchbase News (crawlerbros)",
        "crawlerbros~crunchbase-news-scraper",
        SourceType.news,
        CATEGORY_NEWS,
        {"search": "Australia acquisition", "maxItems": 50},
    ),
    _e(
        "Crunchbase News (nexgendata)",
        "nexgendata~crunchbase-news-scraper",
        SourceType.news,
        CATEGORY_NEWS,
        {
            "category": ["m-a"],
            "date_range": "past_week",
            "limit": 50,
            "keyword_filter": ["Australia"],
        },
    ),
    # ===================================================================
    # CATEGORY 7 - Deal Marketplaces (extra) -> marketplace
    # Generic content crawlers; operator may need to verify the actor id
    # and tune inputs. Degrade to [] gracefully when unavailable.
    # ===================================================================
    _e(
        "Acquire.com (content crawler)",
        "apify~website-content-crawler",
        SourceType.marketplace,
        CATEGORY_DEAL_MARKETPLACES_EXTRA,
        {
            "startUrls": [{"url": "https://acquire.com/"}],
            "maxCrawlPages": 100,
            "maxCrawlDepth": 2,
        },
    ),
    _e(
        "Smergers Australia (content crawler)",
        "apify~website-content-crawler",
        SourceType.marketplace,
        CATEGORY_DEAL_MARKETPLACES_EXTRA,
        {
            "startUrls": [
                {"url": "https://www.smergers.com/businesses-for-sale/australia/"}
            ],
            "maxCrawlPages": 100,
            "maxCrawlDepth": 2,
        },
    ),
    _e(
        "AU Broker Sites (generic crawler)",
        "apify~website-content-crawler",
        SourceType.marketplace,
        CATEGORY_DEAL_MARKETPLACES_EXTRA,
        {
            "startUrls": [
                {"url": "https://www.bsale.com.au/"},
                {"url": "https://www.anybusiness.com.au/"},
                {"url": "https://linkbusiness.com.au/"},
                {"url": "https://www.benchmarkbusiness.com.au/"},
            ],
            "maxCrawlPages": 150,
            "maxCrawlDepth": 2,
        },
    ),
    # ===================================================================
    # CATEGORY 8 - Company Registries -> chamber_directory
    # ===================================================================
    _e(
        "ABR Australian Business Register (generic crawler)",
        "apify~cheerio-scraper",
        SourceType.chamber_directory,
        CATEGORY_COMPANY_REGISTRIES,
        {
            "startUrls": [{"url": "https://abr.business.gov.au/"}],
            "maxRequestsPerCrawl": 100,
        },
    ),
    # ===================================================================
    # CATEGORY 9 - Local Discovery (Google Maps) -> broker_directory
    # ===================================================================
    _e(
        "Google Maps - Brokers & Liquidators (AU)",
        "compass~crawler-google-places",
        SourceType.broker_directory,
        CATEGORY_LOCAL_DISCOVERY,
        {
            "searchStringsArray": [
                "business broker Australia",
                "insolvency liquidator Australia",
                "business sales agent Australia",
            ],
            "maxCrawledPlacesPerSearch": 80,
            "language": "en",
        },
    ),
    # ===================================================================
    # CATEGORY 10 - Social & Search Signals -> social / news
    # NOTE: the X/Twitter actor is a SOCIAL deal-signal source and is NOT a
    # LinkedIn people scraper (is_linkedin stays False); its items flow
    # through the normal pipeline like any other source.
    # ===================================================================
    _e(
        "X / Twitter Deal Signals",
        "apidojo~tweet-scraper",
        SourceType.social,
        CATEGORY_SOCIAL_SEARCH,
        {
            "searchTerms": [
                "business for sale Australia",
                "acquisition Australia SME",
                "franchise for sale Australia",
            ],
            "maxItems": 100,
            "sort": "Latest",
        },
    ),
    _e(
        "Google Search - Deal Signals (AU)",
        "apify~google-search-scraper",
        SourceType.news,
        CATEGORY_SOCIAL_SEARCH,
        {
            "queries": (
                "business for sale Australia\n"
                "manufacturing business acquisition Australia\n"
                "accounting firm for sale Australia"
            ),
            "maxPagesPerQuery": 1,
            "resultsPerPage": 50,
            "countryCode": "au",
        },
    ),
    _e(
        "Indeed - Sector Growth Signal (AU)",
        "misceres~indeed-scraper",
        SourceType.news,
        CATEGORY_SOCIAL_SEARCH,
        {"position": "manufacturing", "country": "AU", "maxItems": 50},
    ),
]


def actor_input_env_var(source_key: str) -> str:
    """Return the per-actor input override env var name for ``source_key``."""

    return f"APIFY_ACTOR_INPUT_{(source_key or '').upper()}"


def resolve_actor_input(entry: ActorEntry) -> dict[str, Any]:
    """Return the run input for ``entry``, honouring an env JSON override.

    If ``APIFY_ACTOR_INPUT_<SOURCE_KEY>`` holds a valid JSON object it replaces
    the default ``input``; otherwise a copy of the default is returned. A
    malformed override is logged and ignored (defaults win) - never fabricated.
    """

    raw = os.environ.get(actor_input_env_var(entry.source_key))
    if raw and raw.strip():
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning(
                "Ignoring malformed %s; using default input for %s.",
                actor_input_env_var(entry.source_key),
                entry.source_key,
            )
        else:
            if isinstance(data, dict):
                return data
            logger.warning(
                "%s is not a JSON object; using default input for %s.",
                actor_input_env_var(entry.source_key),
                entry.source_key,
            )
    return dict(entry.input)


def linkedin_actors() -> list[ActorEntry]:
    """Return the LinkedIn (``is_linkedin``) actors."""

    return [a for a in ACTOR_REGISTRY if a.is_linkedin]


def non_linkedin_actors() -> list[ActorEntry]:
    """Return the non-LinkedIn (deal/news/directory) actors."""

    return [a for a in ACTOR_REGISTRY if not a.is_linkedin]


def actors_by_category() -> dict[str, list[ActorEntry]]:
    """Group the registry by category in :data:`CATEGORY_ORDER`."""

    grouped: dict[str, list[ActorEntry]] = {cat: [] for cat in CATEGORY_ORDER}
    for entry in ACTOR_REGISTRY:
        grouped.setdefault(entry.category, []).append(entry)
    return grouped
