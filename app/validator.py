"""Strict JSON Validator.

Verifies that an assembled output serializes to strict, prose-free JSON whose
top-level keys are exactly ``deals``, ``companies``, ``founders``, ``contacts``
and ``summary``.
"""

from __future__ import annotations

import json
from typing import Any, Union

from .models import ProcessOutput

REQUIRED_TOP_LEVEL_KEYS = {"deals", "companies", "founders", "contacts", "summary"}


def to_strict_json(output: ProcessOutput) -> str:
    """Serialize ``output`` to a strict JSON string with no surrounding prose."""

    return json.dumps(output.model_dump(mode="json"), separators=(",", ":"))


def is_strict_valid_json(output: Union[ProcessOutput, str, dict[str, Any]]) -> bool:
    """Return ``True`` when ``output`` is strict valid JSON with exact keys."""

    if isinstance(output, ProcessOutput):
        payload = output.model_dump(mode="json")
        text = json.dumps(payload)
    elif isinstance(output, str):
        text = output.strip()
        # Reject markdown fences or surrounding prose.
        if not (text.startswith("{") and text.endswith("}")):
            return False
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            return False
    elif isinstance(output, dict):
        payload = output
        try:
            text = json.dumps(payload)
        except (TypeError, ValueError):
            return False
    else:
        return False

    if not isinstance(payload, dict):
        return False
    return set(payload.keys()) == REQUIRED_TOP_LEVEL_KEYS
