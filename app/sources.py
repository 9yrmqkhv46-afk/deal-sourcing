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


def actor_env_var(source_key: str) -> str:
    """Return the canonical Apify-actor environment-variable name for a source.

    The mapping is deterministic: the source key is upper-cased and any
    non-alphanumeric separators (``.`` and ``-``) become underscores, then it is
    prefixed with ``APIFY_ACTOR_``. Examples::

        scaling.com.au        -> APIFY_ACTOR_SCALING_COM_AU
        scalingup.com.au      -> APIFY_ACTOR_SCALINGUP_COM_AU
        businessforsale       -> APIFY_ACTOR_BUSINESSFORSALE
        bsale                 -> APIFY_ACTOR_BSALE
        anybusiness           -> APIFY_ACTOR_ANYBUSINESS
        allbusiness           -> APIFY_ACTOR_ALLBUSINESS
        linkbusiness          -> APIFY_ACTOR_LINKBUSINESS
        sbx                   -> APIFY_ACTOR_SBX
        resolve               -> APIFY_ACTOR_RESOLVE
        benchmark             -> APIFY_ACTOR_BENCHMARK
        businessesforsale_au  -> APIFY_ACTOR_BUSINESSESFORSALE_AU
        franchise2sell        -> APIFY_ACTOR_FRANCHISE2SELL

    This is the *exact* env var an operator must set (alongside ``APIFY_TOKEN``)
    to enable live ingestion for that source.
    """

    normalized = (source_key or "").strip().upper().replace(".", "_").replace("-", "_")
    return f"APIFY_ACTOR_{normalized}"


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
    actor_env: Optional[str] = None,
) -> SourceEntry:
    # Each source resolves its OWN actor id from a deterministic env var name
    # derived from its key (unless one is supplied explicitly).
    return SourceEntry(
        key=key,
        display_name=display_name,
        source_type=source_type,
        base_url=base_url,
        apify_actor_env=actor_env or actor_env_var(key),
    )


# The canonical list of ingestible sources. Apify actor ids are read per-source
# from env vars named by :func:`actor_env_var` (``APIFY_ACTOR_<SOURCE_KEY>``).
_SOURCE_DEFS: list[SourceEntry] = [
    _entry("businessforsale_au", "BusinessForSale.com.au", SourceType.marketplace,
           "https://www.businessforsale.com.au"),
    _entry("bsale", "Bsale", SourceType.marketplace,
           "https://www.bsale.com.au"),
    _entry("anybusiness", "AnyBusiness", SourceType.marketplace,
           "https://www.anybusiness.com.au"),
    _entry("allbusiness_au", "AllBusiness.com.au", SourceType.marketplace,
           "https://www.allbusiness.com.au"),
    _entry("link_business", "LINK Business Brokers", SourceType.broker_directory,
           "https://linkbusiness.com.au"),
    _entry("sbx_business", "SBX Business Brokers", SourceType.broker_directory,
           "https://www.sbxbusiness.com.au"),
    _entry("resolve", "Resolve Marketplace", SourceType.marketplace,
           "https://www.resolve.com.au"),
    _entry("benchmark_business", "Benchmark Business", SourceType.broker_directory,
           "https://www.benchmarkbusiness.com.au"),
    _entry("businessesforsale_au", "BusinessesForSale.com Australia", SourceType.marketplace,
           "https://www.businessesforsale.com/australia"),
    _entry("franchise2sell", "Franchise2Sell", SourceType.marketplace,
           "https://www.franchise2sell.com.au"),
    # Pre-existing paid marketplace source (scaling.com.au) + its sibling.
    _entry("scaling", "Scaling (scaling.com.au)", SourceType.marketplace,
           "https://scaling.com.au"),
    _entry("scalingup.com.au", "ScalingUp (scalingup.com.au)", SourceType.marketplace,
           "https://scalingup.com.au"),
    # Credential-gated social connectors. These MUST only be used with the
    # user's OWN authorized source (official API or an authorized Apify actor)
    # and in compliance with each platform's Terms of Service.
    _entry("linkedin", "LinkedIn", SourceType.social,
           "https://www.linkedin.com"),
    _entry("facebook_groups", "Facebook Groups", SourceType.social,
           "https://www.facebook.com"),
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


# --- Per-source configuration diagnostics -----------------------------------

#: Social sources have their own enable-flag + token gating (NOT just Apify).
_SOCIAL_REQUIRES: dict[str, str] = {
    "linkedin": "linkedin",
    "facebook_groups": "facebook",
}


def apify_token_present() -> bool:
    """Return ``True`` when an ``APIFY_TOKEN`` is configured in the environment."""

    token = os.environ.get("APIFY_TOKEN")
    return bool(token and token.strip())


def _requires(source_key: str) -> str:
    """Return which credential family a source needs: apify/linkedin/facebook."""

    return _SOCIAL_REQUIRES.get(source_key, "apify")


def _note(entry: SourceEntry, requires: str, configured: bool) -> str:
    """Human-friendly guidance for the operator about this source."""

    env = entry.apify_actor_env or actor_env_var(entry.key)
    if requires == "linkedin":
        if configured:
            return "LinkedIn ingestion is enabled and credentialed (use only your own authorized, ToS-compliant source)."
        return (
            "Set LINKEDIN_INGEST_ENABLED=true and provide LINKEDIN_API_TOKEN "
            f"(or APIFY_TOKEN + {env}). Use only your own authorized source, in "
            "compliance with LinkedIn's Terms of Service."
        )
    if requires == "facebook":
        if configured:
            return "Facebook Groups ingestion is enabled and credentialed for your authorized groups."
        return (
            "Set FACEBOOK_INGEST_ENABLED=true, FACEBOOK_API_TOKEN (or APIFY_TOKEN + "
            f"{env}) and FACEBOOK_GROUP_IDS for groups you are authorized to read, "
            "in compliance with Facebook's Terms of Service."
        )
    # Apify-backed marketplace / broker sources.
    if configured:
        return f"Configured: APIFY_TOKEN and {env} are set; live ingestion is enabled."
    if apify_token_present():
        return f"APIFY_TOKEN is set, but {env} is missing. Set it in Render to pull live listings."
    return (
        f"Add an Apify API key (APIFY_TOKEN) and set {env} in Render's Environment "
        "tab to pull live listings from this source."
    )


def _is_configured(source_key: str) -> bool:
    """Resolve a source's configured state via its connector (lazy import).

    Reuses the connectors' own ``is_configured`` logic so this never drifts from
    actual runtime behaviour. Imported lazily to avoid a circular import.
    """

    from .connectors import get_connector  # local import: avoids import cycle

    try:
        return bool(get_connector(source_key).is_configured())
    except Exception:  # pragma: no cover - defensive: never crash diagnostics
        return False


def source_config_status() -> list[dict]:
    """Return per-source configuration diagnostics for every registered source.

    Each entry is a plain dict with::

        {
          "key": str,             # registry key
          "name": str,            # display name
          "source_type": str,     # marketplace | broker_directory | social | ...
          "base_url": str,        # canonical site URL
          "configured": bool,     # ready to ingest live data right now?
          "actor_env_var": str,   # exact env var name to set for this source
          "requires": str,        # "apify" | "linkedin" | "facebook"
          "note": str,            # human-friendly guidance
        }
    """

    statuses: list[dict] = []
    for entry in REGISTRY.all():
        requires = _requires(entry.key)
        configured = _is_configured(entry.key)
        statuses.append(
            {
                "key": entry.key,
                "name": entry.display_name,
                "source_type": entry.source_type.value,
                "base_url": entry.base_url,
                "configured": configured,
                "actor_env_var": entry.apify_actor_env or actor_env_var(entry.key),
                "requires": requires,
                "note": _note(entry, requires, configured),
            }
        )
    return statuses
