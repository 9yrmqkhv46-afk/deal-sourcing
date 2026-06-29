"""Task 4.1 - source-type routing."""

import pytest

from app.config import load_thesis_config
from app.models import SourceItem, SourceType
from app.router import route, select_handler


@pytest.mark.parametrize(
    "stype",
    [
        "marketplace",
        "broker_directory",
        "insolvency_platform",
        "chamber_directory",
        "social",
        "news",
    ],
)
def test_supported_types_dispatch(stype):
    cfg = load_thesis_config()
    item = SourceItem(source_name="Some Source", source_type=stype, raw_text="text")
    handler, resolved = select_handler(item, cfg)
    assert resolved is SourceType(stype)
    assert callable(handler)


def test_scaling_routes_to_marketplace_even_when_declared_social():
    cfg = load_thesis_config()
    item = SourceItem(source_name="scaling.com.au", source_type="social", raw_text="text")
    rf = route(item, cfg)
    assert rf.source_type == "marketplace"


def test_unknown_type_uses_generic_handler():
    cfg = load_thesis_config()
    item = SourceItem(source_name="Blog", source_type="weird_type", raw_text="hello world")
    rf = route(item, cfg)
    # generic handler still extracts a safe title and invents nothing
    assert rf.title == "hello world"
    assert rf.deal_type == "other"
