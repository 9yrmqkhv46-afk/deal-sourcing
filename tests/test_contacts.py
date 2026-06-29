"""Task 9.1 - contact extraction and relevance notes."""

from app.config import load_thesis_config
from app.handlers import RawFields
from app.contacts import build_contacts
from app.models import Founder, FounderRole

CFG = load_thesis_config()


def _rf(contacts):
    return RawFields(
        source_name="scaling.com.au",
        source_type="marketplace",
        external_listing_id_or_url="https://x/1",
        location_text="VIC",
        company={"name": "Co", "country": "Australia", "sector": "manufacturing"},
        contacts=contacts,
    )


def test_broker_contact_built_with_provenance_and_notes():
    rf = _rf([{"person_or_org_name": "Broker B", "role_or_title": "Broker", "deal_size_focus": "10-40M"}])
    contacts = build_contacts([rf], [[]])
    assert len(contacts) == 1
    c = contacts[0]
    assert c.source_name == "scaling.com.au"
    assert c.source_type.value == "marketplace"
    assert c.notes_on_relevance_to_deals is not None
    assert c.priority_reason is None  # unset until surfaced in outreach list


def test_founder_with_handle_becomes_contact():
    rf = _rf([])
    founders = [Founder(name="Jane", role=FounderRole.Founder, email="jane@co.com", tenure_years=22)]
    contacts = build_contacts([rf], [founders])
    assert any(c.person_or_org_name == "Jane" for c in contacts)


def test_founder_without_handle_not_contact():
    rf = _rf([])
    founders = [Founder(name="NoReach", role=FounderRole.Director)]
    contacts = build_contacts([rf], [founders])
    assert contacts == []
