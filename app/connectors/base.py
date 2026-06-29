"""Connector abstract base class.

A :class:`Connector` is a pure adapter from an external source to a list of
:class:`~app.models.SourceItem`. It must be safe to call in any environment:

* When required credentials are missing it MUST return ``[]`` (no-op).
* On any network / HTTP / parsing error it MUST log a warning and return ``[]``.
* It MUST NOT fabricate listings, financials, or contacts.

The returned :class:`SourceItem` objects flow into the EXISTING deterministic
pipeline (ingestion -> route -> handlers -> ... -> assemble), so connectors
never compute scores or write deals themselves.
"""

from __future__ import annotations

import abc
import logging
from typing import Optional

from ..models import SourceItem
from ..sources import REGISTRY, SourceEntry, SourceRegistry

logger = logging.getLogger("app.connectors")


class Connector(abc.ABC):
    """Abstract pure data adapter for one registered source."""

    def __init__(self, source_key: str, registry: Optional[SourceRegistry] = None) -> None:
        self.source_key = source_key
        self._registry = registry or REGISTRY
        self.entry: Optional[SourceEntry] = self._registry.get(source_key)

    @property
    def display_name(self) -> str:
        return self.entry.display_name if self.entry else self.source_key

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Return ``True`` only when the connector has everything it needs."""

    @abc.abstractmethod
    def fetch(self) -> list[SourceItem]:
        """Return source items for the pipeline, or ``[]`` when not configured."""
