"""SQLite persistence for processed snapshots and sync-job status.

Uses the standard-library :mod:`sqlite3` only. The database path is read from
``DATABASE_PATH`` (default ``./data/deal_sourcing.db``); the parent directory is
created on demand. Two tables are maintained:

* ``snapshots`` - the latest processed :class:`~app.models.ProcessOutput`
  serialized as JSON (deals / companies / founders / contacts / summary).
* ``sync_jobs`` - per-source sync status used by the dashboard.

Nothing here performs network access; persistence is fully local and
deterministic given its inputs.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from .models import ProcessOutput

DEFAULT_DB_PATH = "./data/deal_sourcing.db"

_VALID_STATUSES = {"idle", "running", "success", "error", "skipped"}

# Serialize writes from the scheduler thread + request threads.
_LOCK = threading.RLock()


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def db_path() -> str:
    """Return the configured database path (env-overridable)."""

    return os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)


def _connect() -> sqlite3.Connection:
    path = db_path()
    parent = Path(path).expanduser().parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not yet exist."""

    with _LOCK, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        # Backward-compatible snapshot columns (added via ALTER so existing
        # databases pick them up without a destructive migration):
        #   kind          -> "sample_seed" | "live_sync"
        #   synced_at     -> ISO timestamp of the live sync that produced it
        #   linkedin_posts-> JSON list of LinkedInPost dicts attached to the snapshot
        for column_def in (
            "kind TEXT",
            "synced_at TEXT",
            "linkedin_posts TEXT",
        ):
            try:
                conn.execute(f"ALTER TABLE snapshots ADD COLUMN {column_def}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_jobs (
                source_key TEXT PRIMARY KEY,
                job_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                started_at TEXT,
                finished_at TEXT,
                last_sync_at TEXT,
                item_count INTEGER NOT NULL DEFAULT 0,
                message TEXT
            )
            """
        )
        # Backward-compatible diagnostic columns (added via ALTER so existing
        # databases pick them up without a destructive migration).
        for column_def in (
            "fetched_count INTEGER",
            "produced_deal_count INTEGER",
        ):
            try:
                conn.execute(f"ALTER TABLE sync_jobs ADD COLUMN {column_def}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()


#: Valid snapshot kinds. A sample seed is the bundled demo data; a live sync is
#: produced by running the Apify actor registry.
SNAPSHOT_KIND_SAMPLE = "sample_seed"
SNAPSHOT_KIND_LIVE = "live_sync"
_VALID_SNAPSHOT_KINDS = {SNAPSHOT_KIND_SAMPLE, SNAPSHOT_KIND_LIVE}


def save_snapshot(
    output: ProcessOutput,
    *,
    kind: str = SNAPSHOT_KIND_SAMPLE,
    synced_at: Optional[str] = None,
    linkedin_posts: Optional[list[dict[str, Any]]] = None,
) -> None:
    """Persist ``output`` as the latest snapshot (JSON).

    ``kind`` records whether this is the bundled ``sample_seed`` or a
    ``live_sync`` produced by the Apify actor registry. ``synced_at`` is the
    live-sync timestamp (``None`` for the seed). ``linkedin_posts`` is an
    optional list of LinkedInPost dicts attached to a live sync; it is stored
    alongside the strict output (never inside it, so the strict contract is
    untouched).
    """

    if kind not in _VALID_SNAPSHOT_KINDS:
        raise ValueError(f"invalid snapshot kind: {kind!r}")

    payload = json.dumps(output.model_dump(mode="json"), separators=(",", ":"))
    li = json.dumps(linkedin_posts or [], separators=(",", ":"))
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO snapshots (created_at, payload, kind, synced_at, linkedin_posts) "
            "VALUES (?, ?, ?, ?, ?)",
            (_now_iso(), payload, kind, synced_at, li),
        )
        conn.commit()


def load_latest_snapshot() -> Optional[dict[str, Any]]:
    """Return the most recently saved snapshot payload as a dict, or ``None``.

    The returned dict contains EXACTLY the strict output keys (deals,
    companies, founders, contacts, summary) - no metadata is mixed in, so the
    strict contract is preserved. Use :func:`load_latest_snapshot_record` for
    metadata (kind / synced_at / linkedin_posts).
    """

    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload"])
    except (ValueError, TypeError):
        return None


def _row_to_record(row: sqlite3.Row) -> Optional[dict[str, Any]]:
    """Build a rich snapshot record dict from a DB row (payload + metadata)."""

    try:
        payload = json.loads(row["payload"])
    except (ValueError, TypeError):
        return None
    try:
        linkedin_posts = json.loads(row["linkedin_posts"]) if row["linkedin_posts"] else []
    except (ValueError, TypeError):
        linkedin_posts = []
    if not isinstance(linkedin_posts, list):
        linkedin_posts = []
    record = dict(payload)
    record["kind"] = row["kind"] or SNAPSHOT_KIND_SAMPLE
    record["synced_at"] = row["synced_at"]
    record["linkedin_posts"] = linkedin_posts
    return record


def load_latest_snapshot_record() -> Optional[dict[str, Any]]:
    """Return the latest snapshot's payload PLUS metadata, or ``None``.

    Shape: the strict output keys plus ``kind`` (``sample_seed`` /
    ``live_sync``), ``synced_at`` and ``linkedin_posts``.
    """

    try:
        with _LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT payload, kind, synced_at, linkedin_posts "
                "FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except sqlite3.OperationalError:
        return None  # table not created yet
    return _row_to_record(row) if row else None


def load_latest_live_snapshot() -> Optional[dict[str, Any]]:
    """Return the latest ``live_sync`` snapshot record, or ``None``.

    Same shape as :func:`load_latest_snapshot_record` but restricted to
    snapshots produced by a live sync of the Apify actor registry. The live
    GET endpoints read from this so they NEVER serve seeded sample data.
    """

    try:
        with _LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT payload, kind, synced_at, linkedin_posts FROM snapshots "
                "WHERE kind = ? ORDER BY id DESC LIMIT 1",
                (SNAPSHOT_KIND_LIVE,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None  # table not created yet
    return _row_to_record(row) if row else None


def has_snapshot() -> bool:
    """Return ``True`` when at least one snapshot is stored."""

    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT 1 FROM snapshots LIMIT 1").fetchone()
    return row is not None


def upsert_job(
    source_key: str,
    job_name: str,
    status: str,
    *,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    last_sync_at: Optional[str] = None,
    item_count: Optional[int] = None,
    message: Optional[str] = None,
    fetched_count: Optional[int] = None,
    produced_deal_count: Optional[int] = None,
) -> None:
    """Insert or update a sync job's status row.

    Only the fields supplied (non-``None``) overwrite existing values, so a
    ``running`` -> ``success`` transition can preserve the original
    ``started_at`` while updating the rest.
    """

    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    with _LOCK, _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sync_jobs WHERE source_key = ?", (source_key,)
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO sync_jobs
                    (source_key, job_name, status, started_at, finished_at,
                     last_sync_at, item_count, message, fetched_count,
                     produced_deal_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_key,
                    job_name,
                    status,
                    started_at,
                    finished_at,
                    last_sync_at,
                    int(item_count or 0),
                    message,
                    fetched_count,
                    produced_deal_count,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE sync_jobs SET
                    job_name = ?,
                    status = ?,
                    started_at = COALESCE(?, started_at),
                    finished_at = COALESCE(?, finished_at),
                    last_sync_at = COALESCE(?, last_sync_at),
                    item_count = COALESCE(?, item_count),
                    message = COALESCE(?, message),
                    fetched_count = COALESCE(?, fetched_count),
                    produced_deal_count = COALESCE(?, produced_deal_count)
                WHERE source_key = ?
                """,
                (
                    job_name,
                    status,
                    started_at,
                    finished_at,
                    last_sync_at,
                    item_count,
                    message,
                    fetched_count,
                    produced_deal_count,
                    source_key,
                ),
            )
        conn.commit()


def get_job_statuses() -> list[dict[str, Any]]:
    """Return all sync-job rows as dicts (stable order by job_name)."""

    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_jobs ORDER BY job_name, source_key"
        ).fetchall()
    return [
        {
            "source_key": r["source_key"],
            "job_name": r["job_name"],
            "status": r["status"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "last_sync_at": r["last_sync_at"],
            "item_count": r["item_count"],
            "message": r["message"],
            "fetched_count": r["fetched_count"],
            "produced_deal_count": r["produced_deal_count"],
        }
        for r in rows
    ]


def get_overall_last_sync() -> Optional[str]:
    """Return the most recent ``last_sync_at`` across all jobs (ISO) or ``None``."""

    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT MAX(last_sync_at) AS last FROM sync_jobs WHERE last_sync_at IS NOT NULL"
        ).fetchone()
    return row["last"] if row and row["last"] else None
