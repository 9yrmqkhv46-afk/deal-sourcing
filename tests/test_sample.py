"""Task 16.1 - the bundled sample batch processes to valid strict JSON."""

from app.config import load_thesis_config
from app.models import Classification
from app.pipeline import process_batch
from app.sample_data import sample_batch
from app.validator import is_strict_valid_json


def test_sample_produces_core_and_reject():
    out = process_batch(sample_batch(), load_thesis_config())
    assert is_strict_valid_json(out)
    classes = {d.thesis_match.classification for d in out.deals}
    assert Classification.core_thesis in classes
    assert Classification.reject in classes


def test_sample_includes_required_source_families():
    batch = sample_batch()
    names = {item["source_name"] for item in batch}
    types = {item["source_type"] for item in batch}
    assert "scaling.com.au" in names
    assert {"insolvency_platform", "chamber_directory", "social"} <= types
