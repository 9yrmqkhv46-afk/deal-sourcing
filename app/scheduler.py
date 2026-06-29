"""Background scheduler + sync routine for live ingestion.

Uses APScheduler's :class:`BackgroundScheduler` to run a daily sync at fixed
times (default 03:00, 03:15, 03:30, 03:45; configurable via ``SYNC_TIMES``).

The sync routine (:func:`run_sync`) iterates the configured sources, fetches via
each credential-gated connector, runs the EXISTING ``process_batch`` over the
combined :class:`SourceItem` batch, saves a snapshot, and records per-source job
status. A connector that is not credentialed (or hits a network error) simply
contributes no items and is marked ``skipped``; a connector failure never
crashes the app.

The scheduler is guarded by ``SCHEDULER_ENABLED`` (default true) and is force
disabled during tests (``PYTEST_CURRENT_TEST`` / ``TESTING``) so no threads are
spawned in the test suite.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import Optional

from . import store
from .connectors import get_connector
from .models import SourceItem
from .pipeline import process_batch
from .sources import REGISTRY

logger = logging.getLogger("app.scheduler")

DEFAULT_SYNC_TIMES = "03:00,03:15,03:30,03:45"

_scheduler = None  # APScheduler BackgroundScheduler instance when running.


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _truthy(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def scheduler_enabled() -> bool:
    """Scheduler runs only when enabled AND not under test."""

    if os.environ.get("PYTEST_CURRENT_TEST") or _truthy(os.environ.get("TESTING"), False):
        return False
    return _truthy(os.environ.get("SCHEDULER_ENABLED"), True)


def parse_sync_times(raw: Optional[str] = None) -> list[tuple[int, int]]:
    """Parse ``SYNC_TIMES`` (``HH:MM,HH:MM``) into ``(hour, minute)`` tuples."""

    raw = raw if raw is not None else os.environ.get("SYNC_TIMES", DEFAULT_SYNC_TIMES)
    out: list[tuple[int, int]] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            hh, mm = chunk.split(":", 1)
            hour, minute = int(hh), int(mm)
        except ValueError:
            logger.warning("Ignoring malformed SYNC_TIMES entry: %r", chunk)
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            out.append((hour, minute))
    return out or [(3, 0)]


def run_sync(source_keys: Optional[list[str]] = None) -> dict:
    """Run a sync over the given (or all configured) sources.

    Returns a small result dict ``{processed, item_count, sources}``. Never
    raises: any connector error is captured into that source's job status.
    """

    store.init_db()
    keys = source_keys if source_keys is not None else REGISTRY.keys()
    combined: list[SourceItem] = []
    processed_sources: list[str] = []

    for key in keys:
        entry = REGISTRY.get(key)
        job_name = f"sync:{key}"
        display = entry.display_name if entry else key

        connector = get_connector(key)
        if not connector.is_configured():
            store.upsert_job(key, job_name, "skipped", message="skipped: no API key")
            continue

        store.upsert_job(key, job_name, "running", started_at=_now_iso(), message=f"syncing {display}")
        try:
            items = connector.fetch() or []
        except Exception as exc:  # defensive: a connector must never crash sync
            logger.warning("Connector[%s] raised during sync: %s", key, exc)
            store.upsert_job(
                key, job_name, "error", finished_at=_now_iso(), message=f"error: {exc}"
            )
            continue

        combined.extend(items)
        processed_sources.append(key)
        store.upsert_job(
            key,
            job_name,
            "success",
            finished_at=_now_iso(),
            last_sync_at=_now_iso(),
            item_count=len(items),
            message=f"success: {len(items)} items",
        )

    if combined:
        try:
            output = process_batch(combined)
            store.save_snapshot(output)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("process_batch failed during sync: %s", exc)
            return {"processed": False, "item_count": len(combined), "sources": processed_sources}

    return {"processed": bool(combined), "item_count": len(combined), "sources": processed_sources}


def start_scheduler() -> bool:
    """Start the background scheduler if enabled. Returns whether it started."""

    global _scheduler
    if not scheduler_enabled():
        logger.info("Scheduler disabled (env or test mode); not starting.")
        return False
    if _scheduler is not None:
        return True

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except Exception as exc:  # pragma: no cover - dependency missing
        logger.warning("APScheduler unavailable (%s); scheduler not started.", exc)
        return False

    _scheduler = BackgroundScheduler(daemon=True)
    for hour, minute in parse_sync_times():
        _scheduler.add_job(
            run_sync,
            CronTrigger(hour=hour, minute=minute),
            id=f"daily-sync-{hour:02d}{minute:02d}",
            replace_existing=True,
        )
    _scheduler.start()
    logger.info("Scheduler started with daily sync times %s.", parse_sync_times())
    return True


def shutdown_scheduler() -> None:
    """Stop the background scheduler if running."""

    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover - best effort
            pass
        _scheduler = None
