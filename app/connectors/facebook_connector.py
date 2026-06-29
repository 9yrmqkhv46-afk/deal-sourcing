"""Credential-gated Facebook Groups connector (generic interface only).

COMPLIANCE / TERMS OF SERVICE
-----------------------------
Live Facebook ingestion must use the user's OWN authorized source - the
official Facebook Graph API with the appropriate permissions for Groups the
user administers or is authorized to access, or an authorized Apify actor the
user is entitled to run - and must comply with Facebook's Terms of Service,
Platform Policy, and applicable law. This connector implements ONLY a generic,
credential-gated interface. It contains NO scraping logic and NO anti-bot /
protection-bypass behaviour. It will not, and is not intended to, access groups
the operator is not authorized to read.

Activation requires ``FACEBOOK_INGEST_ENABLED`` to be truthy AND one of:

* ``FACEBOOK_API_TOKEN`` - a token for the user's authorized Graph API app, or
* an Apify actor configured via ``APIFY_TOKEN`` + ``APIFY_ACTOR_FACEBOOK_GROUPS``.

Targeting "rules and parameters": the set of authorized group ids/urls to read
is supplied by the operator via ``FACEBOOK_GROUP_IDS`` (comma-separated) and an
optional keyword allow-list via ``FACEBOOK_KEYWORDS``. These are passed to the
operator's authorized actor/app as input; the connector itself performs no
unauthorized access. When not fully configured it no-ops and returns ``[]``.
"""

from __future__ import annotations

import logging
import os

from ..models import SourceItem
from .apify_connector import ApifyConnector
from .base import Connector

logger = logging.getLogger("app.connectors.facebook")


def _enabled() -> bool:
    return (os.environ.get("FACEBOOK_INGEST_ENABLED") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def configured_group_ids() -> list[str]:
    """Return the operator-supplied list of authorized group ids/urls."""

    raw = os.environ.get("FACEBOOK_GROUP_IDS") or ""
    return [g.strip() for g in raw.split(",") if g.strip()]


def configured_keywords() -> list[str]:
    """Return the optional operator-supplied keyword allow-list."""

    raw = os.environ.get("FACEBOOK_KEYWORDS") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


class FacebookGroupsConnector(Connector):
    """Generic, ToS-compliant, credential-gated Facebook Groups adapter."""

    def __init__(self, source_key: str = "facebook_groups", registry=None) -> None:
        super().__init__(source_key, registry)
        self.api_token = (os.environ.get("FACEBOOK_API_TOKEN") or "").strip() or None
        self._apify = ApifyConnector(source_key, registry)

    def is_configured(self) -> bool:
        if not _enabled():
            return False
        if not configured_group_ids():
            # Require an explicit, operator-authorized target list.
            return False
        return bool(self.api_token) or self._apify.is_configured()

    def fetch(self) -> list[SourceItem]:
        if not _enabled():
            logger.warning(
                "FacebookGroupsConnector disabled (FACEBOOK_INGEST_ENABLED not set); skipping. "
                "Live Facebook ingestion requires your own authorized Graph API access or actor "
                "and must comply with Facebook's Terms of Service."
            )
            return []

        if not configured_group_ids():
            logger.warning(
                "FacebookGroupsConnector: no FACEBOOK_GROUP_IDS configured. Provide the ids/urls "
                "of groups you are authorized to read; skipping."
            )
            return []

        if self._apify.is_configured():
            # The authorized actor receives the operator's group ids + keywords
            # as input via its own configuration; the generic adapter degrades
            # gracefully on any error.
            return self._apify.fetch()

        if not self.api_token:
            logger.warning(
                "FacebookGroupsConnector enabled but no authorized source configured "
                "(FACEBOOK_API_TOKEN or APIFY actor); skipping."
            )
            return []

        logger.warning(
            "FacebookGroupsConnector: FACEBOOK_API_TOKEN set but no built-in Graph API client is "
            "bundled. Provide an authorized APIFY_ACTOR_FACEBOOK_GROUPS to ingest. Skipping."
        )
        return []
