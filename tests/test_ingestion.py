"""Task 3.1 - ingestion validation and skip behavior."""

import pytest

from app.ingestion import BatchValidationError, load_batch, validate_source_item


def _item(**over):
    base = {
        "source_name": "scaling.com.au",
        "source_type": "marketplace",
        "raw_text": "some text",
    }
    base.update(over)
    return base


def test_valid_item_passes():
    assert validate_source_item(_item()) is True


@pytest.mark.parametrize("field", ["source_name", "source_type", "raw_text"])
def test_missing_required_field_rejected(field):
    bad = _item()
    bad[field] = ""
    assert validate_source_item(bad) is False
    bad2 = _item()
    del bad2[field]
    assert validate_source_item(bad2) is False


def test_load_batch_counts_skips_and_keeps_valid():
    raw = [_item(), {"source_name": "x"}, _item(source_name="b"), 12345]
    valid, skipped = load_batch(raw)
    assert len(valid) == 2
    assert skipped == 2


def test_non_list_batch_raises():
    with pytest.raises(BatchValidationError):
        load_batch({"not": "a list"})


def test_empty_batch_ok():
    valid, skipped = load_batch([])
    assert valid == [] and skipped == 0
