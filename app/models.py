"""Pydantic v2 data models and enums for the Deal-Sourcing Agent.

These models implement the data contract described in the design document.
Two principles govern every field:

* **Never fabricate data** - every null-eligible field defaults to ``None``
  (or ``"unknown"`` / ``"unknown_date"`` for enum/date-like text).
* **Currency companions** - every currency-bearing numeric amount has a paired
  ``*_currency`` field that must be populated whenever the amount is non-null.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Supported source families for incoming :class:`SourceItem` records."""

    marketplace = "marketplace"
    broker_directory = "broker_directory"
    insolvency_platform = "insolvency_platform"
    chamber_directory = "chamber_directory"
    social = "social"
    news = "news"


class DealType(str, Enum):
    """Kind of opportunity represented by a :class:`Deal`."""

    sale = "sale"
    franchise = "franchise"
    distress = "distress"
    capital_raise = "capital_raise"
    other = "other"


class DealSizeBucket(str, Enum):
    """Enterprise-value size bucket for a :class:`Deal`."""

    small = "small"
    lower_mid = "lower_mid"
    core_mid = "core_mid"
    upper_mid = "upper_mid"
    unknown = "unknown"


class Classification(str, Enum):
    """Final classification outcome for a :class:`Deal`."""

    core_thesis = "core_thesis"
    adjacent_thesis = "adjacent_thesis"
    reject = "reject"


class FounderRole(str, Enum):
    """Role of a key person / :class:`Founder`."""

    Founder = "Founder"
    Director = "Director"
    Partner = "Partner"
    Practitioner = "Practitioner"
    Broker = "Broker"
    Banker = "Banker"


UNKNOWN_DATE = "unknown_date"


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------


class SourceItem(BaseModel):
    """A single pre-fetched input record.

    ``source_name``, ``source_type`` and ``raw_text`` are required and must be
    non-empty for the item to survive ingestion. Optional structured payloads
    let handlers extract fields without parsing raw text.
    """

    model_config = ConfigDict(extra="allow")

    source_name: str
    source_type: str
    raw_text: str
    structured: Optional[dict[str, Any]] = None
    external_listing_id_or_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Output entities
# ---------------------------------------------------------------------------


class Company(BaseModel):
    """A normalized business entity."""

    company_id: str = ""
    name: str
    country: str
    state: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None
    sector: Optional[str] = None
    subsector: Optional[str] = None
    founded_year: Optional[int] = None
    age_years: Optional[int] = None
    employees: Optional[int] = None
    banned_sector_flag: bool = False
    notes_about_business_model: Optional[str] = None


class ThesisMatch(BaseModel):
    """Scoring result embedded inside every :class:`Deal`."""

    deal_id: str = ""
    passes_age_filter: Optional[bool] = None
    passes_sector_filter: Optional[bool] = None
    passes_financial_filter: Optional[bool] = None
    passes_founder_filter: Optional[bool] = None
    ai_automation_potential_flag: Optional[bool] = None
    overall_score: int = 0
    classification: Classification = Classification.reject
    explanation: str = ""


class Deal(BaseModel):
    """A scored, classified opportunity."""

    deal_id: str = ""
    company_id: Optional[str] = None
    source_name: str
    source_type: SourceType
    external_listing_id_or_url: str
    listing_url: Optional[str] = None
    title: str
    description: Optional[str] = None
    deal_type: DealType = DealType.sale
    asking_price: Optional[float] = None
    asking_price_currency: Optional[str] = None
    asking_price_estimated: bool = False
    deal_size_bucket: DealSizeBucket = DealSizeBucket.unknown
    revenue: Optional[float] = None
    revenue_currency: Optional[str] = None
    revenue_estimated: bool = False
    ebitda: Optional[float] = None
    ebitda_currency: Optional[str] = None
    ebitda_estimated: bool = False
    listing_date: Optional[str] = None
    last_seen_at: Optional[str] = None
    location_text: Optional[str] = None
    is_franchise: bool = False
    competitive_notes: Optional[str] = None
    ai_automation_potential_notes: Optional[str] = None
    raw_source_excerpt: str = ""
    is_stale: bool = False
    thesis_match: ThesisMatch = Field(default_factory=ThesisMatch)

    @model_validator(mode="after")
    def _validate_currency_companions(self) -> "Deal":
        """Ensure a ``*_currency`` value is present whenever its amount is set."""
        if self.asking_price is not None and not self.asking_price_currency:
            raise ValueError("asking_price requires asking_price_currency")
        if self.revenue is not None and not self.revenue_currency:
            raise ValueError("revenue requires revenue_currency")
        if self.ebitda is not None and not self.ebitda_currency:
            raise ValueError("ebitda requires ebitda_currency")
        return self


class Founder(BaseModel):
    """A founder or key person."""

    person_id: str = ""
    company_id: Optional[str] = None
    name: str
    role: FounderRole
    start_year: Optional[int] = None
    tenure_years: Optional[int] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    organization_name: Optional[str] = None


class Contact(BaseModel):
    """A relationship lead / intermediary."""

    contact_id: str = ""
    person_or_org_name: str
    role_or_title: Optional[str] = None
    sector_focus: Optional[str] = None
    region_or_state: Optional[str] = None
    linkedin_url: Optional[str] = None
    portal_url_or_website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source_name: str
    source_type: SourceType
    notes_on_relevance_to_deals: Optional[str] = None
    priority_reason: Optional[str] = None


class LinkedInPost(BaseModel):
    """A LinkedIn post surfaced by the credential-gated LinkedIn connector.

    Every field except ``id`` is optional and defaults to ``None`` so the model
    never fabricates author, text, timestamp or URL data it did not receive.
    """

    id: str
    author_name: Optional[str] = None
    author_linkedin_url: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None
    url: Optional[str] = None


class Summary(BaseModel):
    """Aggregate counts and prioritized top lists."""

    core_thesis_deal_count: int = 0
    adjacent_thesis_deal_count: int = 0
    reject_count: int = 0
    top_core_thesis_deals: list[Deal] = Field(default_factory=list)
    top_contacts_for_outreach: list[Contact] = Field(default_factory=list)


class ProcessOutput(BaseModel):
    """The strict JSON output contract."""

    model_config = ConfigDict(extra="forbid")

    deals: list[Deal] = Field(default_factory=list)
    companies: list[Company] = Field(default_factory=list)
    founders: list[Founder] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)


class ProcessRequest(BaseModel):
    """Request body for ``POST /api/process``."""

    batch: list[SourceItem]
    config: Optional[dict[str, Any]] = None
