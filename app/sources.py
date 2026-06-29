"""Source registry for live-ingestion connectors.

This module enumerates the external platforms the agent *can* ingest from when
properly credentialed. It is intentionally separate from the per-request
``ThesisConfig.source_registry`` (which only maps a source *name* to a
:class:`~app.models.SourceType`): this registry additionally carries the base
URL and the optional Apify actor id (read from the environment per source) that
the connector layer needs.

No network access happens here. The registry is pure metadata plus a small URL
helper (:func:`build_listing_url`) used to attach a stable ``listing_url`` to
every deal and a usable link to every contact.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .models import SourceType


@dataclass(frozen=True)
class SourceEntry:
    """Metadata describing one ingestible source platform."""

    key: str
    display_name: str
    source_type: SourceType
    base_url: str
    #: Environment variable name that may hold an Apify actor id for this source.
    apify_actor_env: Optional[str] = None

    @property
    def apify_actor_id(self) -> Optional[str]:
        """Resolve the configured Apify actor id from the environment, if any."""

        if not self.apify_actor_env:
            return None
        value = os.environ.get(self.apify_actor_env)
        return value.strip() if value and value.strip() else None


def _entry(
    key: str,
    display_name: str,
    source_type: SourceType,
    base_url: str,
    actor_env: Optional[str],
) -> SourceEntry:
    return SourceEntry(
        key=key,
        display_name=display_name,
        source_type=source_type,
        base_url=base_url,
        apify_actor_env=actor_env,
    )


# The canonical list of ingestible sources. Apify actor ids are read per-source
# from env vars named APIFY_ACTOR_<SOURCE_KEY_UPPER>.
_SOURCE_DEFS: list[SourceEntry] = [
    _entry("businessforsale_au", "BusinessForSale.com.au", SourceType.marketplace,
           "https://www.businessforsale.com.au", "APIFY_ACTOR_BUSINESSFORSALE_AU"),
    _entry("bsale", "Bsale", SourceType.marketplace,
           "https://www.bsale.com.au", "APIFY_ACTOR_BSALE"),
    _entry("anybusiness", "AnyBusiness", SourceType.marketplace,
           "https://www.anybusiness.com.au", "APIFY_ACTOR_ANYBUSINESS"),
    _entry("allbusiness_au", "AllBusiness.com.au", SourceType.marketplace,
           "https://www.allbusiness.com.au", "APIFY_ACTOR_ALLBUSINESS_AU"),
    _entry("link_business", "LINK Business Brokers", SourceType.broker_directory,
           "https://linkbusiness.com.au", "APIFY_ACTOR_LINK_BUSINESS"),
    _entry("sbx_business", "SBX Business Brokers", SourceType.broker_directory,
           "https://www.sbxbusiness.com.au", "APIFY_ACTOR_SBX_BUSINESS"),
    _entry("resolve", "Resolve Marketplace", SourceType.marketplace,
           "https://www.resolve.com.au", "APIFY_ACTOR_RESOLVE"),
    _entry("benchmark_business", "Benchmark Business", SourceType.broker_directory,
           "https://www.benchmarkbusiness.com.au", "APIFY_ACTOR_BENCHMARK_BUSINESS"),
    _entry("businessesforsale_au", "BusinessesForSale.com Australia", SourceType.marketplace,
           "https://www.businessesforsale.com/australia", "APIFY_ACTOR_BUSINESSESFORSALE_AU"),
    _entry("franchise2sell", "Franchise2Sell", SourceType.marketplace,
           "https://www.franchise2sell.com.au", "APIFY_ACTOR_FRANCHISE2SELL"),
    # Pre-existing paid marketplace source.
    _entry("scaling", "Scaling (scaling.com.au)", SourceType.marketplace,
           "https://scaling.com.au", "APIFY_ACTOR_SCALING"),
    # Credential-gated social connectors. These MUST only be used with the
    # user's OWN authorized source (official API or an authorized Apify actor)
    # and in compliance with each platform's Terms of Service.
    _entry("linkedin", "LinkedIn", SourceType.social,
           "https://www.linkedin.com", "APIFY_ACTOR_LINKEDIN"),
    _entry("facebook_groups", "Facebook Groups", SourceType.social,
           "https://www.facebook.com", "APIFY_ACTOR_FACEBOOK_GROUPS"),
]


class SourceRegistry:
    """An ordered, lookup-friendly collection of :class:`SourceEntry`."""

    def __init__(self, entries: Optional[list[SourceEntry]] = None) -> None:
        self._entries: list[SourceEntry] = list(entries if entries is not None else _SOURCE_DEFS)
        self._by_key: dict[str, SourceEntry] = {e.key: e for e in self._entries}

    def all(self) -> list[SourceEntry]:
        """Return every registered source entry (stable order)."""

        return list(self._entries)

    def keys(self) -> list[str]:
        """Return every registered source key (stable order)."""

        return [e.key for e in self._entries]

    def get(self, source_key: str) -> Optional[SourceEntry]:
        """Return the entry for ``source_key`` or ``None`` when unknown."""

        return self._by_key.get(source_key)


#: Module-level default registry instance.
REGISTRY = SourceRegistry()


def get_source(source_key: str) -> Optional[SourceEntry]:
    """Convenience accessor for the default registry."""

    return REGISTRY.get(source_key)


def resolve_source_key(source_name: Optional[str]) -> Optional[str]:
    """Best-effort map a deal/contact ``source_name`` back to a registry key.

    Matches on (1) exact key, (2) display name (case-insensitive), and
    (3) the base-url host being a substring of the name. Returns ``None`` when
    no confident match exists (so callers avoid fabricating a domain).
    """

    name = (source_name or "").strip().lower()
    if not name:
        return None
    for entry in REGISTRY.all():
        if entry.key == name:
            return entry.key
    for entry in REGISTRY.all():
        if entry.display_name.lower() == name:
            return entry.key
    for entry in REGISTRY.all():
        host = entry.base_url.split("//", 1)[-1].split("/", 1)[0].lower()
        host_root = host[4:] if host.startswith("www.") else host
        if host_root and host_root in name:
            return entry.key
    return None


def build_listing_url(source_key: str, external_listing_id_or_url: Optional[str]) -> Optional[str]:
    """Build a usable listing URL for a source item.

    Rules:

    * If ``external_listing_id_or_url`` is already a full ``http(s)`` URL it is
      returned unchanged.
    * Otherwise the source's ``base_url`` is joined with the external id/path.
    * When the source is unknown and the value is not a URL, ``None`` is
      returned (we never fabricate a domain).
    * When there is no external value at all, the source ``base_url`` is
      returned as a sensible fallback (or ``None`` if the source is unknown).
    """

    value = (external_listing_id_or_url or "").strip()

    if value.lower().startswith(("http://", "https://")):
        return value

    entry = get_source(source_key)
    base = entry.base_url.rstrip("/") if entry else None

    if not value:
        return base

    if base is None:
        return None

    path = value.lstrip("/")
    return f"{base}/{path}"
