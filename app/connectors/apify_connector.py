"""Generic Apify-backed connector.

If ``APIFY_TOKEN`` and the source's actor id (``APIFY_ACTOR_<SOURCE>``) are set
*and* the network is reachable, this connector triggers the Apify actor run,
waits for it to finish, downloads the dataset items, and maps each item into a
:class:`~app.models.SourceItem`.

If any prerequisite is missing, or any network / HTTP error occurs, it logs a
warning and returns ``[]`` - the app then falls back to the seeded / sample
data. It never fabricates listings.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from ..models import SourceItem
from .base import Connector

logger = logging.getLogger("app.connectors.apify")

# Apify REST API base. The run-sync-get-dataset-items endpoint runs the actor
# and returns its dataset items in a single blocking call.
_APIFY_BASE = "https://api.apify.com/v2"
_DEFAULT_TIMEOUT = 60


class ApifyConnector(Connector):
    """Fetch listings for a source via its configured Apify actor."""

    def __init__(self, source_key: str, registry=None) -> None:
        super().__init__(source_key, registry)
        self.token: Optional[str] = (os.environ.get("APIFY_TOKEN") or "").strip() or None

    @property
    def actor_id(self) -> Optional[str]:
        return self.entry.apify_actor_id if self.entry else None

    def is_configured(self) -> bool:
        return bool(self.token and self.actor_id and self.entry)

    def fetch(self) -> list[SourceItem]:
        if not self.is_configured():
            logger.warning(
                "ApifyConnector[%s] not configured (missing token or actor id); skipping.",
                self.source_key,
            )
            return []

        try:
            import requests  # local import so the package imports without requests
        except Exception:  # pragma: no cover - requests is a declared dependency
            logger.warning("requests not available; ApifyConnector[%s] skipping.", self.source_key)
            return []

        actor = self.actor_id.replace("/", "~") if self.actor_id else ""
        url = f"{_APIFY_BASE}/acts/{actor}/run-sync-get-dataset-items"
        try:
            resp = requests.post(
                url,
                params={"token": self.token},
                json={},
                timeout=_DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # network / HTTP / JSON errors all degrade to []
            logger.warning(
                "ApifyConnector[%s] fetch failed (%s); falling back to no data.",
                self.source_key,
                exc,
            )
            return []

        if not isinstance(payload, list):
            logger.warning(
                "ApifyConnector[%s] unexpected payload type %s; skipping.",
                self.source_key,
                type(payload).__name__,
            )
            return []

        return self.map_items(payload)

    def map_items(self, dataset_items: list[dict[str, Any]]) -> list[SourceItem]:
        """Map raw Apify dataset records into :class:`SourceItem` objects.

        Mapping is conservative: only fields that are present are carried, and
        the source name/type come from the registry entry (never invented).
        """

        items: list[SourceItem] = []
        source_name = self.entry.display_name if self.entry else self.source_key
        source_type = self.entry.source_type.value if self.entry else "marketplace"

        for rec in dataset_items:
            if not isinstance(rec, dict):
                continue
            raw_text = self._raw_text(rec)
            if not raw_text:
                continue
            external = self._external_ref(rec)
            structured = self._structured(rec)
            items.append(
                SourceItem(
                    source_name=source_name,
                    source_type=source_type,
                    raw_text=raw_text,
                    structured=structured or None,
                    external_listing_id_or_url=external,
                )
            )
        return items

    @staticmethod
    def _raw_text(rec: dict[str, Any]) -> str:
        for key in ("raw_text", "description", "summary", "text", "title", "name"):
            value = rec.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _external_ref(rec: dict[str, Any]) -> Optional[str]:
        for key in ("url", "listing_url", "external_listing_id_or_url", "link", "id"):
            value = rec.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _structured(rec: dict[str, Any]) -> dict[str, Any]:
        # If the actor already emitted a structured payload, pass it through;
        # otherwise hand the whole record to the handlers as structured input.
        structured = rec.get("structured")
        if isinstance(structured, dict):
            return structured
        return {k: v for k, v in rec.items() if k != "raw_text"}
