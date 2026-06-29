"""Top-level pipeline orchestration: ``batch -> strict JSON output``.

Chains ingestion -> route -> handlers -> normalize -> filters -> score ->
classify -> contacts -> assemble -> validate. The transformation is pure and
deterministic: no randomness, stable sort tie-breakers, and no outbound network
access of any kind.
"""

from __future__ import annotations

from typing import Any, Optional

from . import scoring
from .assembler import ItemRecord, assemble
from .config import ThesisConfig, load_thesis_config
from .contacts import build_contacts
from .handlers import RawFields
from .ingestion import load_batch
from .models import ProcessOutput, SourceItem
from .normalizer import normalize_company, normalize_deal, normalize_founders
from .router import route
from .sources import build_listing_url, resolve_source_key
from .validator import is_strict_valid_json


def enrich_output(output: ProcessOutput) -> ProcessOutput:
    """Attach a ``listing_url`` to every deal and a usable link to contacts.

    This is a pure post-process step: it adds ``listing_url`` *inside* deal
    objects (never a new top-level key) and back-fills
    ``portal_url_or_website`` on contacts that lack any link, using the source
    registry's ``build_listing_url``. Deals whose external ref is already a full
    URL keep that URL unchanged.
    """

    for deal in output.deals:
        key = resolve_source_key(deal.source_name) or ""
        deal.listing_url = build_listing_url(key, deal.external_listing_id_or_url)

    def _backfill(contacts):
        for c in contacts:
            if not (c.portal_url_or_website or c.linkedin_url):
                key = resolve_source_key(c.source_name) or ""
                url = build_listing_url(key, None)
                if url:
                    c.portal_url_or_website = url

    _backfill(output.contacts)
    _backfill(output.summary.top_contacts_for_outreach)
    return output


def process_batch(
    batch: Any,
    config: Optional[ThesisConfig] = None,
) -> ProcessOutput:
    """Run the full pipeline over ``batch`` and return the strict output.

    ``batch`` may be a list of :class:`SourceItem` or raw dicts. ``config`` is
    injected; when omitted a default :class:`ThesisConfig` is loaded.
    """

    cfg = config or load_thesis_config()

    items, _skipped = load_batch(batch)

    records: list[ItemRecord] = []
    rf_list: list[RawFields] = []
    founders_list: list[list] = []

    for item in items:
        rf = route(item, cfg)

        company = normalize_company(rf, cfg)
        deal = normalize_deal(rf, company, cfg)
        founders = normalize_founders(rf, cfg)

        filters = scoring.evaluate_filters(company, deal, founders, cfg)
        penalty = scoring.assess_data_quality(company, deal, founders)
        score = scoring.compute_score(filters, penalty)
        classification = scoring.classify(score, filters, deal, cfg)
        deal.thesis_match = scoring.build_thesis_match(
            filters, score, classification, deal, company, cfg
        )

        records.append(ItemRecord(company=company, deal=deal, founders=founders))
        rf_list.append(rf)
        founders_list.append(founders)

    contacts = build_contacts(rf_list, founders_list)
    output = assemble(records, contacts)
    output = enrich_output(output)

    assert is_strict_valid_json(output), "assembled output failed strict JSON validation"
    return output
