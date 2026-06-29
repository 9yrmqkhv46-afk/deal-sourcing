"""Task 11.1 - strict JSON validator."""

import json

from app.models import ProcessOutput
from app.validator import REQUIRED_TOP_LEVEL_KEYS, is_strict_valid_json, to_strict_json


def test_empty_output_is_valid():
    out = ProcessOutput()
    assert is_strict_valid_json(out) is True
    assert set(json.loads(to_strict_json(out)).keys()) == REQUIRED_TOP_LEVEL_KEYS


def test_dict_with_exact_keys_valid():
    payload = {k: ([] if k != "summary" else {}) for k in REQUIRED_TOP_LEVEL_KEYS}
    assert is_strict_valid_json(payload) is True


def test_missing_key_rejected():
    payload = {"deals": [], "companies": [], "founders": [], "contacts": []}
    assert is_strict_valid_json(payload) is False


def test_extra_key_rejected():
    payload = {k: [] for k in REQUIRED_TOP_LEVEL_KEYS}
    payload["extra"] = 1
    assert is_strict_valid_json(payload) is False


def test_prose_wrapped_json_rejected():
    text = "Here is the output: {\"deals\": []}"
    assert is_strict_valid_json(text) is False


def test_markdown_fence_rejected():
    text = "```json\n{}\n```"
    assert is_strict_valid_json(text) is False
