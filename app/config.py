"""Injected :class:`ThesisConfig` and the source registry.

The configuration is *injected* into the pipeline rather than hard-coded into
logic paths, so thresholds, banned/preferred sector sets and source metadata
(including the paid ``scaling.com.au`` marketplace source) live here.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import SourceType


# Source registry: maps a known source domain/name to its canonical source type.
# scaling.com.au / scalingup.com.au are pre-registered marketplace sources.
SOURCE_REGISTRY: dict[str, SourceType] = {
    "scaling.com.au": SourceType.marketplace,
    "scalingup.com.au": SourceType.marketplace,
}


DEFAULT_BANNED_SECTORS: set[str] = {
    "tobacco",
    "cigarettes",
    "vaping",
    "liquor",
    "alcohol",
    "brewery",
    "winery",
    "distillery",
    "gambling",
    "betting",
    "casino",
    "gaming",
    "wagering",
    "pokies",
}


DEFAULT_PREFERRED_SECTORS: set[str] = {
    "manufacturing",
    "bookkeeping",
    "accounting",
    "financial services",
    "professional services",
    "b2b services",
    "logistics",
    "facilities services",
    "industrial services",
    "engineering services",
    "it services",
    "managed services",
}


class ThesisConfig(BaseModel):
    """Investment-thesis thresholds and reference data."""

    model_config = ConfigDict(extra="forbid")

    current_year: int = Field(default_factory=lambda: _dt.date.today().year)
    current_date: str = Field(
        default_factory=lambda: _dt.date.today().isoformat()
    )
    min_trading_years: int = 6
    min_founder_tenure_years: int = 20
    min_revenue_usd: float = 250_000.0
    min_ebitda_usd: float = 250_000.0
    ev_core_min: float = 10_000_000.0
    ev_core_max: float = 40_000_000.0
    ev_absolute_max: float = 50_000_000.0
    recency_cutoff_months: int = 12
    banned_sectors: set[str] = Field(
        default_factory=lambda: set(DEFAULT_BANNED_SECTORS)
    )
    preferred_sectors: set[str] = Field(
        default_factory=lambda: set(DEFAULT_PREFERRED_SECTORS)
    )
    primary_geography: str = "Australia"
    source_registry: dict[str, SourceType] = Field(
        default_factory=lambda: dict(SOURCE_REGISTRY)
    )


def load_thesis_config(overrides: Optional[dict[str, Any]] = None) -> ThesisConfig:
    """Build a :class:`ThesisConfig`, applying optional injected overrides.

    Determinism note: when no ``current_year`` / ``current_date`` override is
    supplied the defaults derive from today's date. Callers needing fully
    reproducible output should pin both via ``overrides``.
    """

    if not overrides:
        return ThesisConfig()

    data = dict(overrides)
    # Normalize sector sets supplied as lists.
    for key in ("banned_sectors", "preferred_sectors"):
        if key in data and data[key] is not None and not isinstance(data[key], set):
            data[key] = set(data[key])
    return ThesisConfig(**data)


def resolve_source_type(
    source_name: str,
    declared_type: str,
    config: ThesisConfig,
) -> tuple[SourceType, bool]:
    """Resolve the canonical source type for an item.

    Returns a tuple ``(source_type, is_known)``. Registry matches on
    ``source_name`` take precedence (so ``scaling.com.au`` always routes to the
    marketplace handler). Otherwise the declared type is used when it is a valid
    :class:`SourceType`; unknown declared types fall back to ``news`` and report
    ``is_known=False`` so the router can pick the generic handler.
    """

    name_key = (source_name or "").strip().lower()
    for registered_name, registered_type in config.source_registry.items():
        if registered_name.lower() in name_key:
            return registered_type, True

    try:
        return SourceType(declared_type), True
    except ValueError:
        return SourceType.news, False
