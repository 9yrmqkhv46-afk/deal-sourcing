"""Task 10.1 - assembly, summary, and top lists."""

from app.assembler import ItemRecord, assemble, select_top_deals
from app.models import (
    Classification,
    Company,
    Contact,
    Deal,
    SourceType,
    ThesisMatch,
)


def _deal(score, cls, stale=False, ext="u", name="s"):
    return Deal(
        source_name=name,
        source_type=SourceType.marketplace,
        external_listing_id_or_url=ext,
        title="t",
        is_stale=stale,
        thesis_match=ThesisMatch(overall_score=score, classification=cls),
    )


def _company():
    return Company(name="Co", country="Australia")


def _record(score, cls, stale=False, ext="u", name="s"):
    return ItemRecord(company=_company(), deal=_deal(score, cls, stale, ext, name))


def test_ids_unique_and_linked():
    recs = [
        _record(80, Classification.core_thesis, ext="a"),
        _record(50, Classification.adjacent_thesis, ext="b"),
    ]
    out = assemble(recs, [])
    deal_ids = [d.deal_id for d in out.deals]
    company_ids = [c.company_id for c in out.companies]
    assert len(set(deal_ids)) == len(deal_ids)
    assert len(set(company_ids)) == len(company_ids)
    assert out.deals[0].company_id == out.companies[0].company_id


def test_summary_partitions_deals():
    recs = [
        _record(80, Classification.core_thesis, ext="a"),
        _record(50, Classification.adjacent_thesis, ext="b"),
        _record(10, Classification.reject, ext="c"),
    ]
    out = assemble(recs, [])
    s = out.summary
    assert s.core_thesis_deal_count + s.adjacent_thesis_deal_count + s.reject_count == len(out.deals)


def test_top_deals_exclude_stale_and_cap_and_order():
    deals = [
        _deal(90, Classification.core_thesis, ext="a"),
        _deal(95, Classification.core_thesis, stale=True, ext="b"),
        _deal(80, Classification.core_thesis, ext="c"),
        _deal(60, Classification.adjacent_thesis, ext="d"),
    ]
    top = select_top_deals(deals)
    assert all(not d.is_stale for d in top)
    assert all(d.thesis_match.classification is Classification.core_thesis for d in top)
    scores = [d.thesis_match.overall_score for d in top]
    assert scores == sorted(scores, reverse=True)


def test_dedupe_on_source_and_external_ref():
    recs = [
        _record(80, Classification.core_thesis, ext="same", name="s"),
        _record(70, Classification.core_thesis, ext="same", name="s"),
    ]
    out = assemble(recs, [])
    assert len(out.deals) == 1


def test_top_contacts_get_priority_reason():
    contacts = [
        Contact(person_or_org_name="Broker B", role_or_title="Broker",
                source_name="d", source_type=SourceType.broker_directory),
    ]
    recs = [_record(80, Classification.core_thesis)]
    out = assemble(recs, contacts)
    assert len(out.summary.top_contacts_for_outreach) == 1
    assert out.summary.top_contacts_for_outreach[0].priority_reason is not None
    # master list keeps it unset
    assert out.contacts[0].priority_reason is None
