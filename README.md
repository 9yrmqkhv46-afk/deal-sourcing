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
app/connectors/  Credential-gated live-ingestion connectors (Apify, LinkedIn,
              Facebook Groups) — pure data adapters into the existing pipeline
app/sources.py   Source registry + listing-URL builder
app/store.py     SQLite persistence (snapshots + sync-job status)
app/scheduler.py APScheduler daily sync routine
static/       Dashboard (index.html, app.js, styles.css) — no build step
tests/        pytest unit tests + hypothesis property tests (P1–P17)
requirements.txt, render.yaml, Procfile, .gitignore
```

## Live ingestion, scheduling & persistence

The core `/api/process` path remains pure, deterministic and **non-scraping**.
Live ingestion is an additive, **credential-gated** layer that degrades
gracefully: with no credentials (and the sandbox has none) every connector
**no-ops and returns no data**, and the app falls back to the seeded sample
snapshot. Connectors never fabricate listings.

- **Connectors** (`app/connectors/`) are pure adapters returning `SourceItem`s
  for the existing pipeline. `ApifyConnector` calls an Apify actor only when
  `APIFY_TOKEN` and the source's actor id are set and the network is reachable;
  on any missing-credential / network / HTTP error it logs a warning and
  returns `[]`.
- **Scheduler** (`app/scheduler.py`) runs daily syncs at fixed times via
  APScheduler. A sync fetches each configured source, runs `process_batch` over
  the combined batch, and persists a snapshot. The scheduler is disabled
  automatically during tests.
- **Persistence** (`app/store.py`) stores the latest processed snapshot and
  per-source job status in SQLite. On startup, if the DB is empty it is seeded
  by processing the bundled sample batch so the dashboard is populated before
  any live sync.
- **Refresh** re-queries the DB (`/api/refresh`) — it does **not** trigger a
  scrape. The dashboard's "Refresh now" button calls it and polls
  `/api/status` every ~30s to keep per-source badges fresh.

### Environment variables (set these in Render's **Environment** tab)

This service is deployed on **Render**; configure the following in the Render
service's **Environment** tab (none are required — without them live ingestion
simply stays idle and the seeded sample data is served):

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_PATH` | SQLite file path | `./data/deal_sourcing.db` |
| `SCHEDULER_ENABLED` | Enable the daily scheduler | `true` |
| `SYNC_TIMES` | Comma-separated `HH:MM` daily sync times | `03:00,03:15,03:30,03:45` |
| `APIFY_TOKEN` | Apify API token for live actors | _(unset → no-op)_ |
| `APIFY_DEFAULT_ACTOR` | **Single shared actor id** that drives ANY source without its own actor | _(unset)_ |
| `APIFY_ACTOR` | Alias for `APIFY_DEFAULT_ACTOR` (used if the former is unset) | _(unset)_ |
| `APIFY_ACTOR_<SOURCE>` | Per-source Apify actor id (e.g. `APIFY_ACTOR_BSALE`) | _(unset → no-op)_ |
| `LINKEDIN_INGEST_ENABLED` | Enable the LinkedIn connector | `false` |
| `LINKEDIN_API_TOKEN` | Token for your authorized LinkedIn source | _(unset → no-op)_ |
| `FACEBOOK_INGEST_ENABLED` | Enable the Facebook Groups connector | `false` |
| `FACEBOOK_API_TOKEN` | Token for your authorized Facebook Graph API app | _(unset → no-op)_ |
| `FACEBOOK_GROUP_IDS` | Comma-separated ids/urls of groups you are authorized to read | _(unset → no-op)_ |
| `FACEBOOK_KEYWORDS` | Optional keyword allow-list passed to your authorized actor | _(unset)_ |

The daily schedule defaults to **03:00, 03:15, 03:30 and 03:45** server time
and is configurable via `SYNC_TIMES`.

### Per-source Apify actor env vars (set in Render's **Environment** tab)

Live ingestion requires **`APIFY_TOKEN`** (one token for all Apify-backed
sources) **plus** an actor id. Each source resolves its actor id in priority
order:

1. its **own** dedicated env var `APIFY_ACTOR_<SOURCE>`;
2. the shared **default** actor `APIFY_DEFAULT_ACTOR` (or its alias `APIFY_ACTOR`);
3. otherwise it stays idle.

This means a **single uploaded actor** can serve every source at once: set
`APIFY_TOKEN` + `APIFY_DEFAULT_ACTOR` and all sources go live, while any source
you want to specialise can still override the default with its own
`APIFY_ACTOR_<SOURCE>`. A source shows as **Needs API key** in the dashboard's
**Data Sources** panel until both a token and a (specific *or* default) actor
are configured; until then the seeded sample data is served. Set these in the
Render service's **Environment** tab:

| # | Source | Site | Actor env var |
|---|--------|------|---------------|
| 1 | BusinessForSale.com.au | https://www.businessforsale.com.au | `APIFY_ACTOR_BUSINESSFORSALE_AU` |
| 2 | Bsale | https://www.bsale.com.au | `APIFY_ACTOR_BSALE` |
| 3 | AnyBusiness | https://www.anybusiness.com.au | `APIFY_ACTOR_ANYBUSINESS` |
| 4 | AllBusiness.com.au | https://www.allbusiness.com.au | `APIFY_ACTOR_ALLBUSINESS_AU` |
| 5 | LINK Business Brokers | https://linkbusiness.com.au | `APIFY_ACTOR_LINK_BUSINESS` |
| 6 | SBX Business Brokers | https://www.sbxbusiness.com.au | `APIFY_ACTOR_SBX_BUSINESS` |
| 7 | Resolve Marketplace | https://www.resolve.com.au | `APIFY_ACTOR_RESOLVE` |
| 8 | Benchmark Business | https://www.benchmarkbusiness.com.au | `APIFY_ACTOR_BENCHMARK_BUSINESS` |
| 9 | BusinessesForSale.com Australia | https://www.businessesforsale.com/australia | `APIFY_ACTOR_BUSINESSESFORSALE_AU` |
| 10 | Franchise2Sell | https://www.franchise2sell.com.au | `APIFY_ACTOR_FRANCHISE2SELL` |
| 11 | Scaling (scaling.com.au) | https://scaling.com.au | `APIFY_ACTOR_SCALING` |
| 12 | ScalingUp (scalingup.com.au) | https://scalingup.com.au | `APIFY_ACTOR_SCALINGUP_COM_AU` |

> **`APIFY_TOKEN` is required** for every source above — without it all twelve
> stay idle. The LinkedIn and Facebook connectors are **separate** and gated by
> their own enable flags + tokens (`LINKEDIN_INGEST_ENABLED` +
> `LINKEDIN_API_TOKEN`; `FACEBOOK_INGEST_ENABLED` + `FACEBOOK_API_TOKEN` +
> `FACEBOOK_GROUP_IDS`), and may only be used with **your own authorized,
> Terms-of-Service-compliant source** (see the compliance note below).

Inspect live configuration at any time via `GET /api/sources`, which reports
`apify_token_present` plus, for every source, its `configured` flag, the
`actor_source` (`specific` / `default` / `none`), whether an actor id is
resolvable (`resolved_actor_id_present`, value never leaked) and the exact
`actor_env_var` to set. Use the dashboard's **Sync now** button to trigger a
sync; unconfigured sources are reported as `skipped: no API key` (or
`skipped: no actor` when a token is set but no actor is resolvable).

### Apify actor registry (22 actors) — live sync

In addition to the per-source connectors above, the agent ships a fixed
**Apify ACTOR_REGISTRY of 22 actors** (`app/actors.py`). **One `APIFY_TOKEN`
drives all of them** — there are no per-actor tokens. Each actor is run via
Apify's `run-sync-get-dataset-items` endpoint; non-LinkedIn actors map into the
deterministic pipeline as `SourceItem`s, and the four LinkedIn actors map into
`LinkedInPost`s. The actors, grouped by category, map to source types as:

| Category | Actors | `source_type` |
|----------|:------:|---------------|
| AU/Global Business For Sale | 5 | `marketplace` |
| BizBuySell | 4 | `marketplace` |
| AU Directories | 3 | `broker_directory` (ASIC → `chamber_directory`) |
| LinkedIn posts | 4 | `social` (`is_linkedin=true`) |
| M&A intelligence | 3 | `news` |
| News | 3 | `news` |

**Live-sync-then-refresh flow:**

1. The daily scheduler (or **`POST /api/sync`**, which returns `202` immediately
   and runs in the background — it never blocks on the 22 slow actors) iterates
   the registry. Per-actor status is recorded (`success: N items` /
   `fetched 0 items` / `error: <msg>`), and a single failing actor never crashes
   the sync.
2. All collected source items run through `process_batch` **once**; the
   resulting snapshot is stored with `kind="live_sync"` and a `synced_at`
   timestamp, and the LinkedIn posts are attached to it.
3. The dashboard polls `/api/status`, then auto-calls `/api/refresh` to flip
   from sample to **live** data. `/api/refresh` exposes `snapshot_kind`
   (`sample_seed` / `live_sync`) plus `linkedin_posts` so the UI shows a banner:
   *"Showing sample data…"* vs *"Live data • last synced HH:MM"*.

**Live endpoints never return sample data.** `/api/brokers/deals`,
`/api/franchises/deals`, `/api/insolvency/opportunities`, `/api/linkedin/posts`
and `/api/live/today` read from the latest **live** snapshot only. Until a live
sync has run they return empty lists plus a `note` — they never fall back to the
seeded sample (only `/api/refresh` does that).

**Per-actor input override.** Each actor has a sensible default input payload.
To retune one without a code change, set `APIFY_ACTOR_INPUT_<SOURCE_KEY>` to a
JSON object in Render's Environment tab (e.g.
`APIFY_ACTOR_INPUT_AUSTRALIA_BUSINESS_FOR_SALE={"maxItems":50,"location":"Australia"}`);
a malformed value is ignored and the default is used.

> These are **third-party Apify actors** run under the **operator's own Apify
> account and usage** (and billed to it). Review each actor's terms before
> enabling. `GET /api/actors` lists all 22 with their category, source type,
> `is_linkedin` flag, configured state (driven by `APIFY_TOKEN`) and last-run
> message.

### Compliance note — LinkedIn & Facebook (IMPORTANT)

The LinkedIn and Facebook connectors ship as **generic, credential-gated
interfaces only**. They contain **no scraping logic** and **no anti-bot /
protection-bypass behaviour**.

Live ingestion from these platforms must use **your OWN authorized source** —
the platform's official API under an approved application, or an authorized
Apify actor you are entitled to run — and must comply with each platform's
**Terms of Service** and applicable law. For Facebook Groups specifically, you
must only target groups you administer or are otherwise authorized to access,
and you must supply those group ids/urls yourself via `FACEBOOK_GROUP_IDS`. This
project will not access content you are not authorized to read and does not
provide a list of third-party groups to scrape.

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
- `GET  /api/sample` — bundled demo batch
- `GET  /api/sources` — `{ apify_token_present, sources: [ { key, name, source_type, base_url, configured, actor_env_var, actor_source, resolved_actor_id_present, requires, note } ] }`
- `GET  /api/actors` — the 22-actor Apify registry: `{ apify_token_present, categories: [...], actors: [ { name, actor_id, source_key, source_type, category, is_linkedin, configured, message, status, item_count } ] }`
- `POST /api/refresh` — re-query the latest DB snapshot (NOT a scrape) → strict keys + `last_synced_at` + `jobs`
- `GET  /api/status` — `{ last_synced_at, jobs: [...] }` per-source sync status
- `POST /api/sync` — manually trigger a background sync (credential-gated sources still no-op safely)
- `GET  /api/health` — liveness probe

#### Live-data API (additive, live sources only)

These GET endpoints reflect **only live connector data**. Fetched items run
through the same deterministic `process_batch` pipeline; the output is then
shaped to the contracts below. When no live source is configured (or a
configured source returns nothing) they respond with **empty lists plus a clear
`note`** — they do **not** fall back to sample data, and they never fabricate
listings or posts. (`/api/refresh` keeps its seeded-sample behaviour; these
endpoints intentionally do not.)

- `GET /api/brokers/deals?limit=50&country=Australia` — live deals from
  marketplace / broker_directory sources (the 10 AU sites + scaling/scalingup).
- `GET /api/franchises/deals?limit=50&country=Australia` — live deals from the
  franchise source(s) (`franchise2sell`) and/or `is_franchise` listings.
- `GET /api/insolvency/opportunities?country=Australia` — live distress
  opportunities from `insolvency_platform` sources.
- `GET /api/linkedin/posts?country=Australia&since_days=1` — live LinkedIn posts
  via the credential-gated, ToS-compliant connector.
- `GET /api/live/today?country=Australia` — convenience aggregator: brokers +
  franchises (limit 50) + LinkedIn (since_days=1), merged.

**Deal response shape** (brokers / franchises / insolvency):

```json
{
  "deals": [
    {
      "id": "deal_001",
      "source_name": "Bsale",
      "source_url": "https://www.bsale.com.au/listing/555",
      "title": "...",
      "sector": "manufacturing",
      "location": "Sydney, NSW",
      "asking_price": 750000,
      "revenue": 900000,
      "ebitda": 300000,
      "listing_date": "2024-06-01",
      "thesis_match": {
        "passes_age_filter": true,
        "passes_sector_filter": true,
        "passes_financial_filter": true,
        "passes_founder_filter": null,
        "ai_automation_potential_flag": null,
        "overall_score": 72,
        "classification": "core_thesis",
        "explanation": "..."
      }
    }
  ],
  "summary": {
    "core_thesis_deal_count": 1,
    "adjacent_thesis_deal_count": 0,
    "top_core_thesis_deals": ["deal_001"]
  },
  "note": null
}
```

`source_url` is the deal's `listing_url` (source `base_url` + external id).

**LinkedIn response shape** (`/api/linkedin/posts`):

```json
{
  "linkedin_posts": [
    { "id": "...", "author_name": "...", "author_linkedin_url": "...",
      "text": "...", "created_at": "...", "url": "..." }
  ],
  "summary": { "top_linkedin_posts": ["..."] },
  "note": null
}
```

**Today response shape** (`/api/live/today`) merges both: `{ deals,
linkedin_posts, summary { core_thesis_deal_count, adjacent_thesis_deal_count,
top_core_thesis_deals, top_linkedin_posts }, note }`.

**Configuration required:** these endpoints return data only when live sources
are configured (`APIFY_TOKEN` + an actor for deals; for LinkedIn, your own
authorized source — see the LinkedIn compliance note above). With no
credentials they return empty `deals` / `linkedin_posts` plus an explanatory
`note`. LinkedIn ingestion must use **your own authorized API/Apify actor** and
comply with LinkedIn's Terms of Service; no scraping or anti-bot logic is
included.

Example:

```bash
curl -s http://localhost:8000/api/sample \
  | python -c 'import sys,json; print(json.dumps(json.load(sys.stdin)))' \
  | curl -s -X POST http://localhost:8000/api/process \
       -H 'Content-Type: application/json' --data-binary @-
```

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
