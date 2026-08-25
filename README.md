# TransformBiz — Deal-Sourcing & CRM Enrichment Agent

A deterministic, **non-scraping** batch-processing engine for an investment/credit team.
It ingests a batch of **pre-fetched** source items (each carrying `source_name`,
`source_type` and `raw_text`), routes each item to a source-specific handler,
normalizes the content, applies a documented investment thesis (age, sector,
financial, founder and AI-automation filters), scores and classifies every
opportunity, extracts relationship leads, and emits a single **strict JSON**
object for a downstream ETL.

It is shipped as a **FastAPI web service with a no-build-step dashboard**, ready
to push to GitHub and deploy on Render.

## Design principles

- **Never fabricate data** — prefer `null` / `"unknown"` / `"unknown_date"` over guessing.
- **Enforce exclusions strictly** — tobacco, liquor/alcohol-core and gambling are
  always `reject`; deals clearly above ~50M enterprise value are always `reject`;
  deals scoring below 40 are `reject`.
- **No outbound network access** during processing — input is the batch plus an
  injected `ThesisConfig`; output is the JSON contract.
- **Deterministic** — identical input batch + config always yields identical output.

## Strict JSON output contract

Top-level keys are exactly:

```json
{ "deals": [], "companies": [], "founders": [], "contacts": [], "summary": {} }
```

Each `deal` embeds a `thesis_match` with the five tri-state filters, an
`overall_score` in `[0, 100]`, a `classification`
(`core_thesis` / `adjacent_thesis` / `reject`) and a one-paragraph `explanation`.

## Project layout

```
app/          FastAPI app + pure pipeline (ingestion, routing, handlers,
              normalizer, scoring, contacts, assembler, validator, pipeline)
              plus extraction.py (PDF/PPTX -> text) and db.py (persistence)
static/       Dashboard (index.html, app.js, styles.css) — no build step
tests/        pytest unit tests + hypothesis property tests (P1–P17)
requirements.txt, render.yaml, Procfile, .gitignore
```

## Run locally

```bash
# Python 3.11
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# start the service + dashboard
uvicorn app.main:app --reload --port 8000
```

Then open <http://localhost:8000> and click **Load sample data**.

### API

- `GET  /` — dashboard
- `POST /api/process` — body `{ "batch": [ ...source items... ], "config": { ...overrides? } }` → strict JSON output
- `POST /api/upload` — multipart form upload, field `file` (`.pdf` or `.pptx`). Extracts the
  document's text, runs it through the same pipeline as `/api/process` (as a single-item
  batch, `source_type: "document_upload"`), **stores the result in the database**, and returns
  the usual strict JSON output plus a `document_id`.
- `GET  /api/documents` — list previously uploaded documents (filename, upload time, deal count).
- `GET  /api/documents/{document_id}` — a stored document's metadata + every deal found in it.
- `GET  /api/deals` — list deals stored across all uploads (optional `?classification=core_thesis`).
- `GET  /api/sample` — bundled demo batch
- `GET  /api/health` — liveness probe

Example:

```bash
curl -s http://localhost:8000/api/sample \
  | python -c 'import sys,json; print(json.dumps(json.load(sys.stdin)))' \
  | curl -s -X POST http://localhost:8000/api/process \
       -H 'Content-Type: application/json' --data-binary @-
```

## Document upload &amp; storage

Upload a Confidential Information Memorandum, teaser or pitch deck (`.pdf` / `.pptx`) via
the dashboard's **Upload PDF / PPTX** button, or directly:

```bash
curl -s -F "file=@teaser.pdf" http://localhost:8000/api/upload
```

The uploaded file's text is extracted locally (no outbound network access, same as the rest
of the pipeline), run through the existing deterministic scoring pipeline, and both the raw
extracted text and the resulting deals/companies/founders/contacts are saved to the database
so they can be looked up again later — via the dashboard's "Uploaded documents" panel, or
`GET /api/documents` / `GET /api/documents/{id}` / `GET /api/deals`.

Legacy binary `.ppt` files aren't supported (only `.pptx`) — export/save as `.pptx` first.
Scanned/image-only PDFs with no embedded text layer will return a 422 (nothing to extract).

### Database

Storage uses SQLAlchemy against `DATABASE_URL`:

- **Not set** (local dev / a quick demo): falls back to a local SQLite file, `./deals.db`.
- **Set to a Postgres URL** (production): use a managed Postgres database so uploads survive
  redeploys — a web service's local disk (including a SQLite file on it) is wiped on every
  redeploy/restart on both Render and DigitalOcean App Platform.

`render.yaml` provisions a free Render Postgres database and wires its connection string into
`DATABASE_URL` automatically. On DigitalOcean App Platform, add a Dev/Managed Database
component to the app and set `DATABASE_URL` to its connection string (App Platform can inject
this for you when the database is attached to the app).

## Run the tests

```bash
pip install -r requirements.txt
pytest -q
```

The suite covers every filter/score/classify boundary plus the property-based
correctness invariants **P1–P17** (each running at least 100 generated batches).

## Deploy to Render

This repo includes a [`render.yaml`](./render.yaml) blueprint.

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint** and point it at the repo. Render reads
   `render.yaml` and provisions a Python web service:
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check**: `/api/health`
3. Deploy. The dashboard is served at the service root URL.

A [`Procfile`](./Procfile) is also provided for Procfile-based hosts.

## Configuration (injected `ThesisConfig`)

Thresholds and reference data are injected, never hard-coded into logic. Defaults
match the design (6 trading years, 20-year founder tenure, ~250k revenue/EBITDA
floors, 10–40M core EV, 50M absolute max, 12-month recency cutoff, banned and
preferred sector sets, and the `scaling.com.au` / `scalingup.com.au` marketplace
source registry). Override any field per request via the `config` body key.
