"""Ingestion & Batch Loader.

Validates the incoming batch structure and each :class:`SourceItem`. Invalid
items are skipped (never turned into partial / fabricated deals) and counted.
No outbound network access occurs anywhere in this module.
"""

from __future__ import annotations

from typing import Any

from .models import SourceItem


class BatchValidationError(ValueError):
    """Raised when the batch itself is structurally malformed (not a list)."""


def validate_source_item(item: Any) -> bool:
    """Return ``True`` when ``item`` carries the required non-empty fields.

    A valid item must have a non-empty ``source_name``, a present
    ``source_type`` and a non-empty ``raw_text``.
    """

    if isinstance(item, SourceItem):
        data = item.model_dump()
    elif isinstance(item, dict):
        data = item
    else:
        return False

    source_name = data.get("source_name")
    source_type = data.get("source_type")
    raw_text = data.get("raw_text")

    if not isinstance(source_name, str) or not source_name.strip():
        return False
    if not isinstance(source_type, str) or not source_type.strip():
        return False
    if not isinstance(raw_text, str) or not raw_text.strip():
        return False
    return True


def load_batch(raw_batch: Any) -> tuple[list[SourceItem], int]:
    """Validate the batch and return ``(valid_items, skipped_count)``.

    Raises :class:`BatchValidationError` when ``raw_batch`` is not a list. Items
    that fail :func:`validate_source_item` are skipped and counted; processing
    continues with the remaining valid items.
    """

    if not isinstance(raw_batch, list):
        raise BatchValidationError("batch must be a list of source items")

    valid: list[SourceItem] = []
    skipped = 0
    for entry in raw_batch:
        if not validate_source_item(entry):
            skipped += 1
            continue
        if isinstance(entry, SourceItem):
            valid.append(entry)
        else:
            try:
                valid.append(SourceItem(**entry))
            except Exception:
                skipped += 1
    return valid, skipped
