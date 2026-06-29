"""Prioritization & Output Assembler.

Deduplicates entities, assigns stable per-batch IDs, links companies to their
deals/founders, builds the summary and top lists, and produces the final
:class:`ProcessOutput`. All ordering uses stable, deterministic tie-breakers so
identical input yields identical output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    Classification,
    Company,
    Contact,
    Deal,
    Founder,
    ProcessOutput,
    Summary,
)

MAX_TOP_DEALS = 20
MAX_TOP_CONTACTS = 50


@dataclass
class ItemRecord:
    """One source item's normalized entities, kept aligned for linkage."""

    company: Company
    deal: Deal
    founders: list[Founder] = field(default_factory=list)


def _dedupe_records(records: list[ItemRecord]) -> list[ItemRecord]:
    seen: set[tuple[str, str]] = set()
    out: list[ItemRecord] = []
    for rec in records:
        key = (rec.deal.source_name, rec.deal.external_listing_id_or_url)
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def _dedupe_contacts(contacts: list[Contact]) -> list[Contact]:
    seen: set[tuple[str, str, str]] = set()
    out: list[Contact] = []
    for c in contacts:
        key = (c.person_or_org_name, c.source_name, c.email or c.linkedin_url or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def assign_batch_ids(
    records: list[ItemRecord], contacts: list[Contact]
) -> tuple[list[Company], list[Deal], list[Founder], list[Contact]]:
    """Assign unique IDs and link companies to their deals and founders."""

    companies: list[Company] = []
    deals: list[Deal] = []
    founders: list[Founder] = []

    company_counter = 0
    deal_counter = 0
    founder_counter = 0

    for rec in records:
        company_counter += 1
        rec.company.company_id = f"company_{company_counter:03d}"
        companies.append(rec.company)

        deal_counter += 1
        rec.deal.deal_id = f"deal_{deal_counter:03d}"
        rec.deal.company_id = rec.company.company_id
        rec.deal.thesis_match.deal_id = rec.deal.deal_id
        deals.append(rec.deal)

        for fnd in rec.founders:
            founder_counter += 1
            fnd.person_id = f"founder_{founder_counter:03d}"
            fnd.company_id = rec.company.company_id
            founders.append(fnd)

    for i, ct in enumerate(contacts, start=1):
        ct.contact_id = f"contact_{i:03d}"

    return companies, deals, founders, contacts


def select_top_deals(deals: list[Deal]) -> list[Deal]:
    """Top non-stale core_thesis deals, score-descending, capped at 20."""

    eligible = [
        d
        for d in deals
        if d.thesis_match.classification is Classification.core_thesis and not d.is_stale
    ]
    eligible.sort(key=lambda d: (-d.thesis_match.overall_score, d.deal_id))
    return eligible[:MAX_TOP_DEALS]


def _contact_rank(c: Contact) -> int:
    """Deterministic deal-flow likelihood rank (higher = more relevant)."""

    role = (c.role_or_title or "").lower()
    score = 0
    if "broker" in role:
        score += 30
    if "practitioner" in role or "liquidat" in role:
        score += 25
    if "banker" in role:
        score += 20
    if "association" in role or "official" in role:
        score += 10
    if c.sector_focus:
        score += 8
    if c.notes_on_relevance_to_deals:
        score += 5
    if c.email or c.phone:
        score += 4
    return score


def _priority_reason(c: Contact) -> str:
    role = c.role_or_title or "Relationship lead"
    sector = f" focused on {c.sector_focus}" if c.sector_focus else ""
    region = f" in {c.region_or_state}" if c.region_or_state else ""
    return f"{role}{sector}{region}: strong intermediary for sourcing mid-market deal flow."


def select_top_contacts(contacts: list[Contact]) -> list[Contact]:
    """Top contacts by deal-flow likelihood, capped at 50, with priority_reason.

    Returns *copies* carrying ``priority_reason`` so the master contacts list
    keeps ``priority_reason`` unset for non-surfaced contacts.
    """

    ranked = sorted(contacts, key=lambda c: (-_contact_rank(c), c.contact_id))
    top = ranked[:MAX_TOP_CONTACTS]
    out: list[Contact] = []
    for c in top:
        copy = c.model_copy()
        copy.priority_reason = _priority_reason(c)
        out.append(copy)
    return out


def build_summary(deals: list[Deal], contacts: list[Contact]) -> Summary:
    """Build counts and top lists."""

    core = sum(
        1 for d in deals if d.thesis_match.classification is Classification.core_thesis
    )
    adjacent = sum(
        1 for d in deals if d.thesis_match.classification is Classification.adjacent_thesis
    )
    rejected = sum(
        1 for d in deals if d.thesis_match.classification is Classification.reject
    )
    return Summary(
        core_thesis_deal_count=core,
        adjacent_thesis_deal_count=adjacent,
        reject_count=rejected,
        top_core_thesis_deals=select_top_deals(deals),
        top_contacts_for_outreach=select_top_contacts(contacts),
    )


def assemble(records: list[ItemRecord], contacts: list[Contact]) -> ProcessOutput:
    """Dedupe, assign IDs, build the summary, and return the output contract."""

    records = _dedupe_records(records)
    contacts = _dedupe_contacts(contacts)
    companies, deals, founders, contacts = assign_batch_ids(records, contacts)
    summary = build_summary(deals, contacts)
    return ProcessOutput(
        deals=deals,
        companies=companies,
        founders=founders,
        contacts=contacts,
        summary=summary,
    )
