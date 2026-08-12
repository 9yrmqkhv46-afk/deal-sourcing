"""Generic Apify-backed connector.

If ``APIFY_TOKEN`` and an actor id are resolvable (the source's specific
``APIFY_ACTOR_<SOURCE>`` env var, or the shared ``APIFY_DEFAULT_ACTOR`` /
``APIFY_ACTOR`` default) *and* the network is reachable, this connector triggers
the Apify actor run, waits for it to finish, downloads the dataset items, and
maps each item into a :class:`~app.models.SourceItem`.

If any prerequisite is missing, or any network / HTTP error occurs, it logs a
warning and returns ``[]`` - the app then falls back to the seeded / sample
data. It never fabricates listings.

The dataset -> ``SourceItem`` mapping is intentionally **tolerant**: it does not
assume any particular actor schema. It probes a wide set of common field names
to build a human-readable text blob, and *always* appends a compact JSON dump of
the full record so the downstream deterministic pipeline never loses data and
never silently produces empty deals. The mapping helpers (:func:`map_apify_item`
and :func:`pick_first`) are pure and unit-testable.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from ..models import SourceItem, SourceType
from ..sources import SourceEntry, build_listing_url, resolve_actor
from .base import Connector

logger = logging.getLogger("app.connectors.apify")

# Apify REST API base. The run-sync-get-dataset-items endpoint runs the actor
# and returns its dataset items in a single blocking call.
_APIFY_BASE = "https://api.apify.com/v2"
_DEFAULT_TIMEOUT = 60


# --- Tolerant field probing -------------------------------------------------

#: Ordered groups of common field names probed to build a human-readable blob.
#: One value (the first present) is taken from each group, in this order.
_TEXT_FIELD_GROUPS: tuple[tuple[str, ...], ...] = (
    ("title", "name", "heading"),
    ("description", "summary", "body", "details"),
    ("price", "askingPrice", "asking_price"),
    ("revenue", "turnover"),
    ("profit", "ebitda", "netProfit", "cashflow"),
    ("location", "state", "suburb", "address"),
    ("sector", "industry", "category"),
)

#: Common keys (in priority order) that carry a listing URL or id.
_EXTERNAL_REF_KEYS: tuple[str, ...] = (
    "url",
    "link",
    "listingUrl",
    "listing_url",
    "href",
    "detailUrl",
    "id",
    "listingId",
    "external_id",
)


def _coerce_scalar(value: Any) -> str:
    """Coerce an arbitrary value to a clean string (safe for any JSON type)."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def pick_first(item: dict[str, Any], keys: tuple[str, ...] | list[str]) -> Optional[str]:
    """Return the first present, non-empty value among ``keys`` (as a string).

    Values are coerced safely: strings are stripped, numbers/bools stringified,
    and nested dict/list values JSON-encoded. Empty / whitespace-only values are
    skipped. Returns ``None`` when nothing usable is found.
    """

    if not isinstance(item, dict):
        return None
    for key in keys:
        if key not in item:
            continue
        text = _coerce_scalar(item.get(key))
        if text:
            return text
    return None


def _human_blob(item: dict[str, Any]) -> str:
    """Concatenate the first value from each common field group, when present."""

    parts: list[str] = []
    for group in _TEXT_FIELD_GROUPS:
        value = pick_first(item, group)
        if value:
            parts.append(value)
    return "\n".join(parts)


def _json_dump(item: dict[str, Any]) -> str:
    """Compact, deterministic JSON dump of the full record (never raises)."""

    try:
        return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(item)


def has_signal(item: dict[str, Any]) -> bool:
    """Return ``True`` when a record carries any recognizable listing signal.

    A record with neither an external ref/id nor any known content field is
    treated as junk and skipped (so truly-empty records never become deals).
    """

    if not isinstance(item, dict):
        return False
    if pick_first(item, _EXTERNAL_REF_KEYS):
        return True
    return any(pick_first(item, group) for group in _TEXT_FIELD_GROUPS)


def _structured_passthrough(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Carry through structured hints for the pipeline (never fabricated).

    If the actor already emitted a ``structured`` dict, use it; otherwise hand
    the whole record (minus ``raw_text``) to the handlers as structured input.
    """

    structured = item.get("structured")
    if isinstance(structured, dict):
        return structured or None
    passthrough = {k: v for k, v in item.items() if k != "raw_text"}
    return passthrough or None


def map_apify_item(item: dict[str, Any], source: SourceEntry) -> SourceItem:
    """Map one Apify dataset record into a :class:`SourceItem` (pure).

    * ``source_name`` / ``source_type`` come from the registry entry.
    * ``external_listing_id_or_url`` is the first present of the common URL/id
      keys; a bare id is combined with the source ``base_url`` via
      :func:`~app.sources.build_listing_url`.
    * ``raw_text`` is a human-readable blob of common fields **plus** an always-
      present compact JSON dump of the full record, so downstream extraction
      never loses data.
    * Structured hints are carried through when available; the pipeline remains
      the source of truth (missing values stay null - nothing is fabricated).
    """

    raw_ref = pick_first(item, _EXTERNAL_REF_KEYS)
    external = build_listing_url(source.key, raw_ref)

    blob = _human_blob(item)
    dump = _json_dump(item)
    raw_text = f"{blob}\n{dump}" if blob else dump

    return SourceItem(
        source_name=source.display_name,
        source_type=source.source_type.value,
        raw_text=raw_text,
        structured=_structured_passthrough(item),
        external_listing_id_or_url=external,
    )


@dataclass
class ActorRunResult:
    """The outcome of a single Apify actor run.

    * ``items``       - the dataset records (always a list of dicts; ``[]`` on
      any failure so callers never need to null-check).
    * ``ok``          - ``True`` only when the run completed and returned a
      well-formed dataset list.
    * ``error``       - a short, human-readable failure description (status code
      + a snippet of Apify's response body, a timeout / network message, ...),
      or ``None`` on success.
    * ``status_code`` - the HTTP status code when one was received, else
      ``None``.

    Behaves like a small mapping for convenience: ``result["ok"]`` works as well
    as ``result.ok``.
    """

    items: list[dict[str, Any]]
    ok: bool
    error: Optional[str]
    status_code: Optional[int]

    def __getitem__(self, key: str) -> Any:  # dict-style access convenience
        return getattr(self, key)

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "ok": self.ok,
            "error": self.error,
            "status_code": self.status_code,
        }


#: Short, human-friendly hints for the common Apify run-sync failure codes.
_STATUS_HINTS: dict[int, str] = {
    400: "bad request",
    401: "Unauthorized: token invalid",
    402: "payment required / usage limit",
    403: "forbidden: token lacks access",
    404: "actor not found",
    408: "run timed out",
    413: "dataset too large",
    429: "rate limited",
    500: "Apify server error",
    502: "Apify bad gateway",
    503: "Apify service unavailable",
}


def _body_snippet(text: Optional[str], limit: int = 180) -> str:
    """Return a compact, single-line snippet of a response body (never raises)."""

    if not text:
        return ""
    snippet = " ".join(str(text).split())
    if len(snippet) > limit:
        snippet = snippet[:limit].rstrip() + "..."
    return snippet


def _http_error_message(status: int, body: Optional[str], actor_id: str) -> str:
    """Build a real, actionable error string from an HTTP failure.

    Examples: ``"401 Unauthorized: token invalid"``,
    ``"404 actor not found: owner~name"``, ``"408 run timed out"``,
    ``"413 dataset too large"`` - always with a snippet of Apify's body when one
    is present.
    """

    hint = _STATUS_HINTS.get(status, "request failed")
    if status == 404:
        hint = f"actor not found: {actor_id}"
    snippet = _body_snippet(body)
    message = f"{status} {hint}"
    if snippet:
        message = f"{message}: {snippet}"
    return message


def run_actor_result(
    actor_id: str,
    run_input: dict[str, Any],
    token: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> ActorRunResult:
    """Run an Apify actor and return a rich :class:`ActorRunResult`.

    POSTs ``run_input`` to
    ``https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items`` with
    the token as a query parameter. Unlike the legacy :func:`run_actor` wrapper,
    this surfaces the REAL failure detail instead of silently degrading to ``[]``:

    * HTTP error -> ``ok=False`` with the status code AND a short snippet of
      Apify's response body in ``error`` (e.g. ``"401 Unauthorized: token
      invalid"``, ``"404 actor not found: <id>"``, ``"408 run timed out"``,
      ``"413 dataset too large"``).
    * Timeout    -> ``error="timeout after <N>s"``.
    * Connection -> ``error="network error: <msg>"``.

    It NEVER raises and NEVER fabricates data, so a single bad actor can never
    crash a live sync. ``actor_id`` may be ``owner/name`` or ``owner~name``; it
    is normalized to the ``~`` form the REST path expects.
    """

    if not actor_id or not token:
        return ActorRunResult(
            items=[],
            ok=False,
            error="missing actor id or token",
            status_code=None,
        )

    try:
        import requests  # local import so the package imports without requests
    except Exception:  # pragma: no cover - requests is a declared dependency
        return ActorRunResult(
            items=[], ok=False, error="requests library not available", status_code=None
        )

    actor = actor_id.replace("/", "~")
    url = f"{_APIFY_BASE}/acts/{actor}/run-sync-get-dataset-items"

    try:
        resp = requests.post(
            url,
            params={"token": token},
            json=run_input or {},
            timeout=timeout,
        )
    except Exception as exc:  # network / timeout errors -> explicit messages
        name = type(exc).__name__.lower()
        if "timeout" in name:
            error = f"timeout after {timeout}s"
        else:
            error = f"network error: {exc}"
        logger.warning("run_actor[%s] %s", actor_id, error)
        return ActorRunResult(items=[], ok=False, error=error, status_code=None)

    status = getattr(resp, "status_code", None)
    if isinstance(status, int) and status >= 400:
        body = getattr(resp, "text", "") or ""
        error = _http_error_message(status, body, actor)
        logger.warning("run_actor[%s] failed: %s", actor_id, error)
        return ActorRunResult(items=[], ok=False, error=error, status_code=status)

    try:
        payload = resp.json()
    except Exception as exc:  # malformed JSON body
        error = f"invalid JSON response: {exc}"
        logger.warning("run_actor[%s] %s", actor_id, error)
        return ActorRunResult(items=[], ok=False, error=error, status_code=status)

    if not isinstance(payload, list):
        error = f"unexpected payload type: {type(payload).__name__}"
        logger.warning("run_actor[%s] %s", actor_id, error)
        return ActorRunResult(items=[], ok=False, error=error, status_code=status)

    items = [rec for rec in payload if isinstance(rec, dict)]
    return ActorRunResult(items=items, ok=True, error=None, status_code=status)


def run_actor(
    actor_id: str,
    run_input: dict[str, Any],
    token: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Run an Apify actor and return its dataset items (list[dict]).

    Thin backward-compatible wrapper around :func:`run_actor_result`: it returns
    just ``result.items`` (``[]`` on any failure) so existing callers / tests
    keep working. Use :func:`run_actor_result` when you need the real error.
    """

    return run_actor_result(actor_id, run_input, token, timeout).items


def map_dataset_items(dataset_items: list[dict[str, Any]], source: SourceEntry) -> list[SourceItem]:
    """Map raw Apify dataset records into :class:`SourceItem` objects (pure).

    Non-dict records and records carrying no recognizable listing signal are
    skipped; every other record is mapped tolerantly via :func:`map_apify_item`.
    This is the shared mapping used by both the per-source connector and the
    registry-driven live sync.
    """

    items: list[SourceItem] = []
    for rec in dataset_items:
        if not isinstance(rec, dict):
            continue
        if not has_signal(rec):
            continue
        items.append(map_apify_item(rec, source))
    return items


class ApifyConnector(Connector):
    """Fetch listings for a source via its resolved Apify actor."""

    def __init__(self, source_key: str, registry=None) -> None:
        super().__init__(source_key, registry)
        self.token: Optional[str] = (os.environ.get("APIFY_TOKEN") or "").strip() or None

    @property
    def actor_id(self) -> Optional[str]:
        """Resolve actor id: source-specific env var -> default actor -> None."""

        actor, _ = resolve_actor(self.source_key)
        return actor

    @property
    def actor_source(self) -> str:
        """Where the actor id came from: ``specific`` / ``default`` / ``none``."""

        _, source = resolve_actor(self.source_key)
        return source

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

        Non-dict records and records carrying no recognizable listing signal are
        skipped; every other record is mapped tolerantly via
        :func:`map_apify_item`.
        """

        source = self.entry or SourceEntry(
            key=self.source_key,
            display_name=self.source_key,
            source_type=SourceType.marketplace,
            base_url="",
        )
        items: list[SourceItem] = []
        for rec in dataset_items:
            if not isinstance(rec, dict):
                continue
            if not has_signal(rec):
                continue
            items.append(map_apify_item(rec, source))
        return items
