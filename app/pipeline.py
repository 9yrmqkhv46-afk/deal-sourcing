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
from .validator import is_strict_valid_json


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

    assert is_strict_valid_json(output), "assembled output failed strict JSON validation"
    return output
