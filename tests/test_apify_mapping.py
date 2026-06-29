"""Unit tests for the tolerant Apify dataset -> SourceItem mapping helpers.

These exercise the *pure* functions ``map_apify_item`` and ``pick_first`` with
no network and no credentials. The central guarantee under test: every mapped
item yields parseable ``raw_text`` that always embeds a JSON dump of the full
record, so the downstream pipeline never silently produces empty deals.
"""

import json

import pytest

from app.connectors.apify_connector import (
    has_signal,
    map_apify_item,
    pick_first,
)
from app.models import SourceItem, SourceType
from app.sources import get_source


SOURCE = get_source("bsale")  # display "Bsale", base https://www.bsale.com.au


# --- pick_first priority + coercion -----------------------------------------

def test_pick_first_returns_first_present_key():
    item = {"link": "https://x/y", "url": "https://a/b"}
    # "url" has priority over "link" in the external-ref list, but pick_first
    # itself honours the *given* key order.
    assert pick_first(item, ("url", "link")) == "https://a/b"
    assert pick_first(item, ("link", "url")) == "https://x/y"


def test_pick_first_skips_empty_and_whitespace():
    item = {"title": "   ", "name": "Real Name"}
    assert pick_first(item, ("title", "name")) == "Real Name"


def test_pick_first_coerces_non_string_values():
    assert pick_first({"id": 777}, ("id",)) == "777"
    assert pick_first({"price": 750000.0}, ("price",)) == "750000"
    assert pick_first({"flag": True}, ("flag",)) == "True"


def test_pick_first_returns_none_when_absent():
    assert pick_first({"a": 1}, ("b", "c")) is None
    assert pick_first("not-a-dict", ("a",)) is None


# --- map_apify_item: full schema --------------------------------------------

def test_map_full_schema_item():
    item = {
        "title": "Established Manufacturing Business",
        "description": "Profitable plant in Victoria, manual scheduling.",
        "askingPrice": 4200000,
        "revenue": 3100000,
        "ebitda": 850000,
        "location": "Victoria",
        "sector": "Manufacturing",
        "url": "https://www.bsale.com.au/listing/42",
    }
    si = map_apify_item(item, SOURCE)
    assert isinstance(si, SourceItem)
    assert si.source_name == "Bsale"
    assert si.source_type == SourceType.marketplace.value
    assert si.external_listing_id_or_url == "https://www.bsale.com.au/listing/42"
    # Human-readable fields appear in the blob.
    for fragment in ("Manufacturing Business", "Victoria", "Manufacturing"):
        assert fragment in si.raw_text
    # JSON dump is always appended and is itself valid JSON.
    dump = si.raw_text.split("\n")[-1]
    assert json.loads(dump)["askingPrice"] == 4200000


def test_map_minimal_item_title_and_url():
    item = {"title": "Small bookkeeping firm", "url": "https://www.bsale.com.au/x/9"}
    si = map_apify_item(item, SOURCE)
    assert si.external_listing_id_or_url == "https://www.bsale.com.au/x/9"
    assert "Small bookkeeping firm" in si.raw_text
    assert '"title":"Small bookkeeping firm"' in si.raw_text


def test_map_item_with_only_id_builds_url_from_base():
    item = {"id": "listing-123"}
    si = map_apify_item(item, SOURCE)
    # A bare id is combined with the source base_url.
    assert si.external_listing_id_or_url == "https://www.bsale.com.au/listing-123"
    # raw_text still carries the JSON dump even with no human fields.
    assert '"id":"listing-123"' in si.raw_text


def test_external_ref_priority_url_beats_id():
    item = {"id": "999", "url": "https://www.bsale.com.au/real"}
    si = map_apify_item(item, SOURCE)
    assert si.external_listing_id_or_url == "https://www.bsale.com.au/real"


def test_external_ref_listingurl_variants():
    item = {"listingUrl": "https://www.bsale.com.au/lu", "id": "1"}
    si = map_apify_item(item, SOURCE)
    assert si.external_listing_id_or_url == "https://www.bsale.com.au/lu"


def test_map_handles_nested_and_non_string_values():
    item = {
        "title": {"en": "Nested Title"},   # nested dict
        "price": 1000000,                  # int
        "revenue": 250000.0,               # float
        "tags": ["m&a", "au"],             # list
        "id": 555,                         # non-string id
    }
    si = map_apify_item(item, SOURCE)
    # Does not raise; produces a valid SourceItem.
    assert isinstance(si, SourceItem)
    # Bare numeric id resolves against base_url.
    assert si.external_listing_id_or_url == "https://www.bsale.com.au/555"
    # The JSON dump round-trips the nested structure.
    dump = si.raw_text.split("\n")[-1]
    parsed = json.loads(dump)
    assert parsed["title"] == {"en": "Nested Title"}
    assert parsed["tags"] == ["m&a", "au"]


def test_raw_text_always_contains_json_dump_even_with_no_text_fields():
    item = {"externalReferenceCode": "X", "id": "abc"}
    si = map_apify_item(item, SOURCE)
    dump = si.raw_text.split("\n")[-1]
    assert json.loads(dump) == {"externalReferenceCode": "X", "id": "abc"}


def test_structured_passthrough_carries_hints():
    item = {"title": "T", "url": "https://www.bsale.com.au/1", "asking_price": 500000}
    si = map_apify_item(item, SOURCE)
    assert si.structured is not None
    assert si.structured.get("asking_price") == 500000


def test_structured_uses_explicit_structured_block_when_present():
    item = {"title": "T", "structured": {"revenue": 300000, "revenue_currency": "AUD"}}
    si = map_apify_item(item, SOURCE)
    assert si.structured == {"revenue": 300000, "revenue_currency": "AUD"}


# --- has_signal -------------------------------------------------------------

def test_has_signal_true_for_content_or_ref():
    assert has_signal({"title": "x"}) is True
    assert has_signal({"id": "1"}) is True
    assert has_signal({"category": "Manufacturing"}) is True


def test_has_signal_false_for_junk():
    assert has_signal({"nothing_useful": True}) is False
    assert has_signal({}) is False
    assert has_signal("not-a-dict") is False
