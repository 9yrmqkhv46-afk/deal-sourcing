"""FastAPI service exposing the Processing_Endpoint and the dashboard.

Routes
------
* ``GET  /``                     -> serves the static dashboard.
* ``POST /api/process``          -> runs the pipeline over ``{batch, config?}``
  and returns the strict JSON output contract.
* ``POST /api/upload``           -> extracts text from an uploaded PDF/PPTX,
  runs it through the same pipeline, stores the result and returns it.
* ``GET  /api/documents``        -> lists previously uploaded documents.
* ``GET  /api/documents/{id}``   -> a stored document + its extracted deals.
* ``GET  /api/deals``            -> lists deals stored across all uploads.
* ``GET  /api/sample``           -> returns the bundled demo batch.
* ``GET  /api/health``           -> liveness probe.

The ``ThesisConfig`` is injected per request (with optional overrides from the
request body) rather than hard-coded into the logic. No outbound network calls
are made while handling a request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import load_thesis_config
from .extraction import UnsupportedFileType, extract_text
from .ingestion import BatchValidationError
from .models import ProcessRequest, SourceItem
from .pipeline import process_batch
from .sample_data import sample_batch

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# Reject absurdly large uploads before we even try to parse them.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

app = FastAPI(
    title="Deal-Sourcing & CRM Enrichment Agent (TransformBiz)",
    version="1.0.0",
    description=(
        "Deterministic, non-scraping batch processor that transforms pre-fetched "
        "source items into a strict JSON deal/contact contract."
    ),
)


@app.on_event("startup")
def _on_startup() -> None:
    db.init_db()


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


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    """Extract text from an uploaded PDF/PPTX, process it and store the result.

    The file is treated as a single-item batch (``source_type`` is set to
    ``document_upload``, which has no dedicated handler, so it is routed to
    the conservative generic handler — no financial figures are ever guessed
    from raw document text). The resulting deals/companies/founders/contacts
    are stored so they can be looked up again later via ``GET /api/documents``.
    """

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 25MB upload limit")
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    filename = file.filename or "upload"
    try:
        raw_text = extract_text(filename, data)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=400, detail=f"could not read file: {exc}") from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No extractable text found in the document (it may be a scanned/image-only file)",
        )

    item = SourceItem(source_name=filename, source_type="document_upload", raw_text=raw_text)
    config = load_thesis_config()
    output = process_batch([item], config)

    company_name_by_id = {c.company_id: c.name for c in output.companies}
    doc = db.save_upload_result(
        filename=filename,
        content_type=file.content_type,
        file_size_bytes=len(data),
        raw_text=raw_text,
        output=output,
        company_name_by_id=company_name_by_id,
    )

    return JSONResponse(
        content={"document_id": doc.id, "filename": doc.filename, **output.model_dump(mode="json")}
    )


@app.get("/api/documents")
def get_documents(limit: int = 100, offset: int = 0) -> dict[str, list]:
    """List previously uploaded documents (most recent first), no deal detail."""

    docs = db.list_documents(limit=limit, offset=offset)
    return {"documents": [db.document_to_dict(d, include_deals=False) for d in docs]}


@app.get("/api/documents/{document_id}")
def get_document_detail(document_id: str) -> dict:
    """A stored document's metadata plus every deal extracted from it."""

    doc = db.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return db.document_to_dict(doc, include_deals=True)


@app.get("/api/deals")
def get_deals(classification: Optional[str] = None, limit: int = 200, offset: int = 0) -> dict[str, list]:
    """List deals stored across all uploaded documents, most recent first."""

    rows = db.list_deal_records(classification=classification, limit=limit, offset=offset)
    return {"deals": [db.deal_record_to_dict(r) for r in rows]}


# Mount static assets last so API routes take precedence.
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
