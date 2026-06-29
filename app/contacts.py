"""Contact & Relationship Extractor.

Builds :class:`Contact` records for brokers, liquidators, bankers, founders and
association officials, annotating ``notes_on_relevance_to_deals`` when derivable.
``priority_reason`` is deliberately left unset here - it is assigned only when a
contact is surfaced in ``top_contacts_for_outreach`` by the assembler.
"""

from __future__ import annotations

from typing import Any, Optional

from .handlers import RawFields
from .models import Contact, Founder, SourceType


def _relevance_note(raw: dict[str, Any], rf: RawFields) -> Optional[str]:
    bits: list[str] = []
    role = raw.get("role_or_title")
    sector = raw.get("sector_focus") or (rf.company or {}).get("sector")
    region = raw.get("region_or_state") or rf.location_text
    size = raw.get("deal_size_focus")
    if role:
        bits.append(f"Acts as {role}")
    if sector:
        bits.append(f"sector focus: {sector}")
    if size:
        bits.append(f"deal size: {size}")
    if region:
        bits.append(f"region: {region}")
    if not bits:
        return None
    return "; ".join(bits) + "."


def build_contacts(rf_list: list[RawFields], founders_list: list[list[Founder]]) -> list[Contact]:
    """Build contacts from handler-extracted dicts and founder records.

    ``rf_list`` and ``founders_list`` are aligned per source item.
    """

    contacts: list[Contact] = []

    for rf in rf_list:
        try:
            stype = SourceType(rf.source_type)
        except ValueError:
            stype = SourceType.news
        for raw in rf.contacts:
            name = raw.get("person_or_org_name") or raw.get("name")
            if not name:
                continue
            contacts.append(
                Contact(
                    person_or_org_name=name,
                    role_or_title=raw.get("role_or_title"),
                    sector_focus=raw.get("sector_focus") or (rf.company or {}).get("sector"),
                    region_or_state=raw.get("region_or_state") or rf.location_text,
                    linkedin_url=raw.get("linkedin_url"),
                    portal_url_or_website=raw.get("portal_url_or_website") or rf.external_listing_id_or_url,
                    email=raw.get("email"),
                    phone=raw.get("phone"),
                    source_name=rf.source_name,
                    source_type=stype,
                    notes_on_relevance_to_deals=_relevance_note(raw, rf),
                )
            )

    # Founders with outreach handles become contacts too.
    for rf, founders in zip(rf_list, founders_list):
        try:
            stype = SourceType(rf.source_type)
        except ValueError:
            stype = SourceType.news
        for founder in founders:
            if not (founder.email or founder.linkedin_url or founder.phone):
                continue
            note = f"Founder/{founder.role.value}"
            if founder.tenure_years is not None:
                note += f" with ~{founder.tenure_years} years tenure"
            note += "."
            contacts.append(
                Contact(
                    person_or_org_name=founder.name,
                    role_or_title=founder.role.value,
                    sector_focus=(rf.company or {}).get("sector"),
                    region_or_state=rf.location_text,
                    linkedin_url=founder.linkedin_url,
                    email=founder.email,
                    phone=founder.phone,
                    source_name=rf.source_name,
                    source_type=stype,
                    notes_on_relevance_to_deals=note,
                )
            )

    return contacts
