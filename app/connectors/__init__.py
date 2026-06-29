"""Live-ingestion connectors.

Every connector is a *pure data adapter*: it fetches (or no-ops) and returns a
list of :class:`~app.models.SourceItem` for the EXISTING deterministic pipeline
to process. Connectors never write deals directly and never fabricate data.

All connectors degrade gracefully: when their required credentials are absent,
or any network / HTTP error occurs, they log a warning and return ``[]`` so the
app falls back to the seeded / sample data.
"""

from __future__ import annotations

from typing import Optional

from .apify_connector import ApifyConnector
from .base import Connector
from .facebook_connector import FacebookGroupsConnector
from .linkedin_connector import LinkedInConnector

# Map a source_key -> connector factory. A sync job iterates configured sources
# and instantiates the right connector for each. Social platforms get their own
# credential-gated connector; everything else uses the generic Apify adapter.
_SPECIAL: dict[str, type[Connector]] = {
    "linkedin": LinkedInConnector,
    "facebook_groups": FacebookGroupsConnector,
}


def get_connector(source_key: str) -> Connector:
    """Return a connector instance for ``source_key``.

    Social sources map to their dedicated credential-gated connectors; all
    other registered sources use the generic :class:`ApifyConnector`.
    """

    cls = _SPECIAL.get(source_key)
    if cls is not None:
        return cls(source_key)
    return ApifyConnector(source_key)


__all__ = [
    "Connector",
    "ApifyConnector",
    "LinkedInConnector",
    "FacebookGroupsConnector",
    "get_connector",
]
