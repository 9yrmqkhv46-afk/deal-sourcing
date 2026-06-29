"""FastAPI service exposing the Processing_Endpoint and the dashboard.

Routes
------
* ``GET  /``            -> serves the static dashboard.
* ``POST /api/process`` -> runs the pipeline over ``{batch, config?}`` and
  returns the strict JSON output contract.
* ``GET  /api/sample``  -> returns the bundled demo batch.
* ``GET  /api/health``  -> liveness probe.

The ``ThesisConfig`` is injected per request (with optional overrides from the
request body) rather than hard-coded into the logic. No outbound network calls
are made while handling a request.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_thesis_config
from .ingestion import BatchValidationError
from .models import ProcessRequest
from .pipeline import process_batch
from .sample_data import sample_batch

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Deal-Sourcing & CRM Enrichment Agent (TransformBiz)",
    version="1.0.0",
    description=(
        "Deterministic, non-scraping batch processor that transforms pre-fetched "
        "source items into a strict JSON deal/contact contract."
    ),
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


# Mount static assets last so API routes take precedence.
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
