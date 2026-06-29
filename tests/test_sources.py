"""Tests for the source registry and listing-URL builder."""

from app.models import SourceType
from app.sources import (
    REGISTRY,
    build_listing_url,
    get_source,
    resolve_source_key,
)


REQUIRED_MARKETPLACE_AND_BROKER = {
    "businessforsale_au",
    "bsale",
    "anybusiness",
    "allbusiness_au",
    "link_business",
    "sbx_business",
    "resolve",
    "benchmark_business",
    "businessesforsale_au",
    "franchise2sell",
}


def test_registry_contains_all_ten_plus_social_sources():
    keys = set(REGISTRY.keys())
    # The 10 specified platforms ...
    assert REQUIRED_MARKETPLACE_AND_BROKER.issubset(keys)
    # ... plus the existing scaling source and the social connectors.
    assert "scaling" in keys
    assert "linkedin" in keys
    assert "facebook_groups" in keys


def test_social_sources_are_typed_social():
    assert get_source("linkedin").source_type is SourceType.social
    assert get_source("facebook_groups").source_type is SourceType.social


def test_build_listing_url_passes_through_full_urls():
    full = "https://www.bsale.com.au/listing/12345"
    assert build_listing_url("bsale", full) == full
    http = "http://example.com/x"
    assert build_listing_url("anybusiness", http) == http


def test_build_listing_url_joins_base_and_id():
    url = build_listing_url("businessforsale_au", "listing/987")
    assert url == "https://www.businessforsale.com.au/listing/987"
    # Leading slash on the path is handled.
    url2 = build_listing_url("bsale", "/abc")
    assert url2 == "https://www.bsale.com.au/abc"


def test_build_listing_url_no_external_returns_base():
    assert build_listing_url("resolve", None) == "https://www.resolve.com.au"


def test_build_listing_url_unknown_source_without_url_returns_none():
    assert build_listing_url("nope", "some-id") is None


def test_resolve_source_key_by_name_and_domain():
    assert resolve_source_key("scaling.com.au") == "scaling"
    assert resolve_source_key("LinkedIn") == "linkedin"
    assert resolve_source_key("BusinessForSale.com.au") == "businessforsale_au"
    assert resolve_source_key("totally unknown source") is None
