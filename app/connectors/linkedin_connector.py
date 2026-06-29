"""Credential-gated LinkedIn connector (generic interface only).

COMPLIANCE / TERMS OF SERVICE
-----------------------------
Live LinkedIn ingestion must use the user's OWN authorized source - either the
official LinkedIn API under an approved application, or an authorized Apify
actor the user is entitled to run - and must comply with LinkedIn's Terms of
Service and applicable law. This connector deliberately implements only a
generic, credential-gated interface. It contains NO scraping logic and NO
anti-bot / protection-bypass behaviour of any kind.

Activation requires ``LINKEDIN_INGEST_ENABLED`` to be truthy AND one of:

* ``LINKEDIN_API_TOKEN`` - a token for the user's authorized API source, or
* an Apify actor configured via ``APIFY_TOKEN`` + ``APIFY_ACTOR_LINKEDIN``.

When not fully configured the connector no-ops and returns ``[]`` so the app
falls back to seeded / sample data. It never fabricates posts or contacts.
"""

from __future__ import annotations

import logging
import os

from ..models import SourceItem
from .apify_connector import ApifyConnector
from .base import Connector

logger = logging.getLogger("app.connectors.linkedin")


def _enabled() -> bool:
    return (os.environ.get("LINKEDIN_INGEST_ENABLED") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


class LinkedInConnector(Connector):
    """Generic, ToS-compliant, credential-gated LinkedIn adapter."""

    def __init__(self, source_key: str = "linkedin", registry=None) -> None:
        super().__init__(source_key, registry)
        self.api_token = (os.environ.get("LINKEDIN_API_TOKEN") or "").strip() or None
        # Reuse the generic Apify adapter when an authorized actor is configured.
        self._apify = ApifyConnector(source_key, registry)

    def is_configured(self) -> bool:
        if not _enabled():
            return False
        return bool(self.api_token) or self._apify.is_configured()

    def fetch(self) -> list[SourceItem]:
        if not _enabled():
            logger.warning(
                "LinkedInConnector disabled (LINKEDIN_INGEST_ENABLED not set); skipping. "
                "Live LinkedIn ingestion requires your own authorized source and ToS compliance."
            )
            return []

        # Prefer an authorized Apify actor when configured; the generic adapter
        # already degrades gracefully on any error.
        if self._apify.is_configured():
            return self._apify.fetch()

        if not self.api_token:
            logger.warning(
                "LinkedInConnector enabled but no authorized source configured "
                "(LINKEDIN_API_TOKEN or APIFY actor); skipping."
            )
            return []

        # An official-API integration would call the user's authorized endpoint
        # here. We intentionally ship no built-in scraping; without an actor we
        # safely no-op rather than guess at a private integration.
        logger.warning(
            "LinkedInConnector: LINKEDIN_API_TOKEN set but no built-in API client is "
            "bundled. Provide an authorized APIFY_ACTOR_LINKEDIN to ingest. Skipping."
        )
        return []
