"""Source-Type Router.

Dispatches each :class:`SourceItem` to the handler matching its resolved source
type. Registry matches (e.g. ``scaling.com.au`` -> marketplace) take precedence
over the declared ``source_type``. Unknown declared types fall back to the
generic handler.
"""

from __future__ import annotations

from typing import Callable

from . import handlers
from .config import ThesisConfig, resolve_source_type
from .handlers import RawFields
from .models import SourceItem, SourceType

HandlerFn = Callable[[SourceItem], RawFields]

_HANDLERS: dict[SourceType, HandlerFn] = {
    SourceType.marketplace: handlers.handle_marketplace,
    SourceType.broker_directory: handlers.handle_broker_directory,
    SourceType.insolvency_platform: handlers.handle_insolvency_platform,
    SourceType.chamber_directory: handlers.handle_chamber_directory,
    SourceType.social: handlers.handle_social_or_news,
    SourceType.news: handlers.handle_social_or_news,
}


def select_handler(item: SourceItem, config: ThesisConfig) -> tuple[HandlerFn, SourceType]:
    """Return the ``(handler, resolved_source_type)`` for ``item``."""

    resolved, is_known = resolve_source_type(
        item.source_name, item.source_type, config
    )
    if not is_known:
        return handlers.handle_generic, resolved
    return _HANDLERS[resolved], resolved


def route(item: SourceItem, config: ThesisConfig) -> RawFields:
    """Dispatch ``item`` to its handler and return the extracted RawFields.

    The resolved source type is written back onto the RawFields so downstream
    stages and the output contract reflect the canonical type (e.g. a
    ``scaling.com.au`` item declared as ``social`` still becomes marketplace).
    """

    handler, resolved = select_handler(item, config)
    rf = handler(item)
    rf.source_type = resolved.value
    return rf
