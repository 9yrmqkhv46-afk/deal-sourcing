"""FastAPI service exposing the Processing_Endpoint and the dashboard.

Routes
------
* ``GET  /``            -> serves the static dashboard.
* ``POST /api/process`` -> runs the pipeline over ``{batch, config?}`` and
  returns the strict JSON output contract.
* ``GET  /api/sample``  -> returns the bundled demo batch.
* ``GET  /api/sources`` -> per-source config diagnostics (configured vs needs-key
  plus the exact actor env var to set) for the dashboard's Data Sources panel.
* ``POST /api/refresh`` -> re-queries the DB (NOT a re-scrape) and returns the
  latest snapshot plus ``last_synced_at`` and per-source ``jobs``.
* ``GET  /api/status``  -> returns ``last_synced_at`` + per-source job status.
* ``POST /api/sync``    -> manually triggers a background sync (credential-gated
  sources still no-op safely) and returns the current status.
* ``GET  /api/health``  -> liveness probe.

The ``ThesisConfig`` is injected per request (with optional overrides from the
request body) rather than hard-coded into the logic. The synchronous
``/api/process`` path makes no outbound network calls; live ingestion happens
only via the scheduler / ``/api/sync`` and is fully credential-gated.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import live
from . import store
from .config import load_thesis_config
from .ingestion import BatchValidationError
from .models import ProcessRequest
from .pipeline import process_batch
from .sample_data import sample_batch
from .scheduler import (
    parse_sync_times,
    run_live_sync,
    run_sync,
    scheduler_enabled,
    shutdown_scheduler,
    start_scheduler,
)
from .sources import apify_token_present, source_config_status
from .actors import ACTOR_REGISTRY, CATEGORY_ORDER

logger = logging.getLogger("app.main")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


def seed_if_empty() -> dict:
    """Seed the DB by processing the bundled sample batch when it is empty.

    Returns the latest snapshot dict (existing or freshly seeded).
    """

    store.init_db()
    snapshot = store.load_latest_snapshot()
    if snapshot is None:
        logger.info("DB empty; seeding from bundled sample batch.")
        output = process_batch(sample_batch())
        store.save_snapshot(output)
        store.upsert_job(
            "seed", "seed:sample", "success",
            last_sync_at=store.get_overall_last_sync(),
            item_count=len(output.deals),
            message="seeded from bundled sample data",
        )
        snapshot = store.load_latest_snapshot()
    return snapshot or {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure DB exists + is seeded, then (optionally) start scheduler.
    try:
        seed_if_empty()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Seeding failed at startup: %s", exc)
    start_scheduler()
    yield
    # Shutdown: stop the scheduler cleanly.
    shutdown_scheduler()


app = FastAPI(
    title="Deal-Sourcing & CRM Enrichment Agent (TransformBiz)",
    version="1.1.0",
    description=(
        "Deterministic, non-scraping batch processor that transforms pre-fetched "
        "source items into a strict JSON deal/contact contract, with credential-"
        "gated live ingestion, daily scheduling and SQLite persistence."
    ),
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the dashboard."""

    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sample")
def get_sample() -> dict[str, list]:
    """Return the bundled demo batch the dashboard can load."""

    return {"batch": sample_batch()}


@app.get("/api/sources")
def sources() -> JSONResponse:
    """Return per-source configuration diagnostics for the dashboard.

    Shape::

        {
          "apify_token_present": bool,
          "sources": [ { key, name, source_type, base_url, configured,
                         actor_env_var, requires, note }, ... ]
        }

    The UI uses this to show which sources are live ("Configured") versus which
    still need an API key, including the exact env var name to set.
    """

    return JSONResponse(
        content={
            "apify_token_present": apify_token_present(),
            "sources": source_config_status(),
        }
    )


@app.get("/api/actors")
def actors() -> JSONResponse:
    """Return the 30-actor Apify registry grouped for the Data Sources panel.

    Shape::

        {
          "apify_token_present": bool,
          "categories": [ ...ordered category labels... ],
          "actors": [ { name, actor_id, source_key, source_type, category,
                        is_linkedin, configured, message }, ... ]
        }

    ``configured`` is simply whether ``APIFY_TOKEN`` is present (one token
    drives every actor). ``message`` is the actor's last sync-job message, if
    any. Actor input payloads are never leaked.
    """

    token_present = apify_token_present()
    store.init_db()
    jobs = {j["source_key"]: j for j in store.get_job_statuses()}
    actors_out = []
    for entry in ACTOR_REGISTRY:
        job = jobs.get(entry.source_key) or {}
        actors_out.append(
            {
                "name": entry.name,
                "actor_id": entry.actor_id,
                "source_key": entry.source_key,
                "source_type": entry.source_type.value,
                "category": entry.category,
                "is_linkedin": entry.is_linkedin,
                "configured": token_present,
                "message": job.get("message"),
                "status": job.get("status"),
                "item_count": job.get("item_count"),
            }
        )
    return JSONResponse(
        content={
            "apify_token_present": token_present,
            "categories": list(CATEGORY_ORDER),
            "actors": actors_out,
        }
    )


@app.post("/api/process")
def process(request: ProcessRequest) -> JSONResponse:
    """Run the pipeline and return the strict JSON output contract."""

    if not isinstance(request.batch, list):
        raise HTTPException(status_code=422, detail="batch must be a list of source items")

    try:
        config = load_thesis_config(request.config)
        output = process_batch(request.batch, config)
    except BatchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=400, detail=f"processing error: {exc}") from exc

    return JSONResponse(content=output.model_dump(mode="json"))


@app.post("/api/refresh")
def refresh() -> JSONResponse:
    """Re-query the DB for the latest snapshot (NOT a re-scrape).

    Returns the strict output keys plus ``last_synced_at``, ``jobs``,
    ``snapshot_kind`` (``sample_seed`` / ``live_sync`` so the UI can tell the
    user whether they are viewing live or sample data) and ``linkedin_posts``
    when a live sync attached any. If the DB is empty it is seeded from the
    bundled sample batch first.
    """

    store.init_db()
    record = store.load_latest_snapshot_record()
    if record is None:
        seed_if_empty()
        record = store.load_latest_snapshot_record()

    record = record or {}
    linkedin_posts = record.pop("linkedin_posts", []) if isinstance(record, dict) else []
    snapshot_kind = record.pop("kind", store.SNAPSHOT_KIND_SAMPLE)
    record.pop("synced_at", None)

    body = dict(record)
    body["snapshot_kind"] = snapshot_kind
    body["linkedin_posts"] = linkedin_posts
    body["last_synced_at"] = store.get_overall_last_sync()
    body["jobs"] = store.get_job_statuses()
    return JSONResponse(content=body)


@app.get("/api/status")
def status() -> JSONResponse:
    """Return the overall last sync time and per-source job status."""

    store.init_db()
    return JSONResponse(
        content={
            "last_synced_at": store.get_overall_last_sync(),
            "jobs": store.get_job_statuses(),
        }
    )


@app.post("/api/sync")
def sync(background_tasks: BackgroundTasks) -> JSONResponse:
    """Manually trigger a background sync.

    Credential-gated sources still no-op safely. This endpoint NEVER returns a
    500: scheduling the background task is wrapped in a guard so a transient
    error still yields a clean 202 with ``accepted`` + a ``message``. The
    current job status is included so the UI can begin polling immediately.
    """

    accepted = True
    message = "sync started"
    try:
        store.init_db()
        background_tasks.add_task(run_live_sync)
    except Exception as exc:  # pragma: no cover - defensive: never 500 on sync
        logger.warning("Failed to schedule live sync: %s", exc)
        accepted = False
        message = f"could not start sync: {exc}"

    last_synced_at = None
    jobs: list = []
    try:
        last_synced_at = store.get_overall_last_sync()
        jobs = store.get_job_statuses()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read job status during sync: %s", exc)

    return JSONResponse(
        status_code=202,
        content={
            "accepted": accepted,
            "message": message,
            "last_synced_at": last_synced_at,
            "jobs": jobs,
        },
    )


@app.get("/api/diagnostics")
def diagnostics() -> JSONResponse:
    """Operator diagnostics: confirm the Apify token works from this host.

    Reports whether an ``APIFY_TOKEN`` is present (and its length only - never
    the value). When a token is present it calls Apify's ``/v2/users/me``
    endpoint with a short timeout to verify validity, returning the resolved
    username when the token is good. On ANY network / HTTP error it returns
    ``token_valid=false`` with a clear message - it never raises or 500s.

    Shape::

        {
          "token_present": bool,
          "token_length": int,
          "token_valid": true | false | null,   # null when no token to test
          "apify_user": <username> | null,
          "http_status": int | null,
          "message": str,
          "scheduler_enabled": bool,
          "sync_times": ["HH:MM", ...],
          "actor_count": int,
        }
    """

    token = (os.environ.get("APIFY_TOKEN") or "").strip()
    token_present = bool(token)

    try:
        sync_times = [f"{h:02d}:{m:02d}" for h, m in parse_sync_times()]
    except Exception:  # pragma: no cover - defensive
        sync_times = []

    body: dict = {
        "token_present": token_present,
        "token_length": len(token),
        "token_valid": None,
        "apify_user": None,
        "http_status": None,
        "message": "",
        "scheduler_enabled": scheduler_enabled(),
        "sync_times": sync_times,
        "actor_count": len(ACTOR_REGISTRY),
    }

    if not token_present:
        body["message"] = "No APIFY_TOKEN configured; set it in the environment to enable live sync."
        return JSONResponse(content=body)

    try:
        import requests  # local import so the package imports without requests

        resp = requests.get(
            "https://api.apify.com/v2/users/me",
            params={"token": token},
            timeout=10,
        )
        body["http_status"] = getattr(resp, "status_code", None)
        status = body["http_status"]
        if isinstance(status, int) and 200 <= status < 300:
            username = None
            try:
                data = resp.json()
                if isinstance(data, dict):
                    payload = data.get("data") if isinstance(data.get("data"), dict) else data
                    username = payload.get("username") or payload.get("id")
            except Exception:  # pragma: no cover - tolerate odd bodies
                username = None
            body["token_valid"] = True
            body["apify_user"] = username
            body["message"] = (
                f"Token is valid (Apify user: {username})." if username else "Token is valid."
            )
        else:
            body["token_valid"] = False
            if status == 401:
                body["message"] = "Apify rejected the token (401 Unauthorized) - it is invalid or expired."
            else:
                body["message"] = f"Apify returned HTTP {status}; token could not be verified."
    except Exception as exc:
        body["token_valid"] = False
        body["message"] = f"Could not reach Apify to verify the token: {exc}"

    return JSONResponse(content=body)


# ---------------------------------------------------------------------------
# Live-data API (ADDITIVE). These GET endpoints reflect ONLY live connector
# data: they run fetched items through the existing pipeline and shape the
# output. When no live source is configured they return empty lists plus a
# clear ``note`` (NO sample fallback). They never fabricate listings or posts.
# ---------------------------------------------------------------------------


@app.get("/api/brokers/deals")
def brokers_deals(limit: int = 50, country: str = "Australia") -> JSONResponse:
    """Live broker / marketplace deals (marketplace + broker_directory sources)."""

    return JSONResponse(content=live.brokers_deals(limit=limit, country=country))


@app.get("/api/franchises/deals")
def franchises_deals(limit: int = 50, country: str = "Australia") -> JSONResponse:
    """Live franchise deals (franchise source(s) / is_franchise listings)."""

    return JSONResponse(content=live.franchises_deals(limit=limit, country=country))


@app.get("/api/insolvency/opportunities")
def insolvency_opportunities(country: str = "Australia") -> JSONResponse:
    """Live insolvency / distress opportunities (insolvency_platform sources)."""

    return JSONResponse(content=live.insolvency_opportunities(country=country))


@app.get("/api/linkedin/posts")
def linkedin_posts(country: str = "Australia", since_days: int = 1) -> JSONResponse:
    """Live LinkedIn posts via the ToS-compliant, credential-gated connector."""

    return JSONResponse(content=live.linkedin_posts(country=country, since_days=since_days))


@app.get("/api/live/today")
def live_today(country: str = "Australia") -> JSONResponse:
    """Aggregated "today" view: brokers + franchises + LinkedIn posts merged."""

    return JSONResponse(content=live.live_today(country=country))


# Mount static assets last so API routes take precedence.
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
