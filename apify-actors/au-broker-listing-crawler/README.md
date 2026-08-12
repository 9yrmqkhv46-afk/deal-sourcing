# AU Broker Listing Crawler

One generic, input-configured Apify actor that can serve **every** AU
business-broker / business-for-sale site the deal-sourcing agent cares about,
instead of one bespoke (and, as this project already learned the hard way,
one blindly-guessed) actor per site. Site-specific behaviour comes entirely
from the actor's **input** — `startUrls`, plus optional `itemLinkPattern` /
`itemSelector` overrides — so you deploy this **once** and reuse it across
all 10–12 sites by giving each a different input.

## Why generic instead of 12 bespoke actors

The deal-sourcing agent originally wired up 30 third-party Apify Store
actors compiled from AI-assisted research. Several had wrong/guessed input
fields (rejected with `400 invalid-input`), and the whole batch eventually
hit an account-level `403 Monthly usage hard limit exceeded`. Writing 12
more actors the same way — guessing CSS selectors for sites this project
has no network access to inspect — would repeat the same failure mode, just
with different error messages.

Instead, this actor extracts from things that are unusually **stable**
across independently-built sites rather than guessed CSS classes:

- JSON-LD structured data (`<script type="application/ld+json">`), if the
  site emits it (many do, for SEO).
- Open Graph meta tags (`og:title`, `og:description`, `og:price:amount`).
- `<h1>` / `<title>` for the listing title.
- Regex heuristics for AUD prices (`$1,250,000`) and Australian state
  abbreviations (prefers `City, STATE` over a bare state code, to avoid
  false-positives on titles like "Packaging Manufacturer VIC").
- A generic "does this link look like a listing detail page" heuristic
  (skips nav/login/contact/legal links; prefers links with slug- or
  id-shaped hrefs and title-length anchor text) — overridable with an exact
  `itemLinkPattern` substring once a human has actually looked at the site.

**This was verified end-to-end against a local test HTTP server** (list
page → 2 real listings + 3 nav links + 1 robots.txt-disallowed link) before
being committed: it correctly followed only the 2 real listings, correctly
skipped the nav links and the disallowed one, and correctly extracted
title/description/price/location/JSON-LD from both a JSON-LD-rich page and
a plain-HTML page. It has **not** been run against any real broker site
(this project's sandbox cannot reach the public internet), so treat the
first run against each real site as a test, with `maxItems` kept small.

## Output shape

Each pushed dataset record matches the deal-sourcing agent's existing
tolerant field-probing, so no changes are needed on the consuming side:

```json
{
  "url": "https://example.com/listing/...",
  "title": "Established Packaging Manufacturer - VIC",
  "description": "Profitable packaging business...",
  "askingPrice": "$1,250,000",
  "location": "Melbourne, VIC",
  "jsonLd": [ { "...": "..." } ],
  "raw_text": "full extracted page text, for the pipeline's own extraction"
}
```

## Deploy it

You'll need the [Apify CLI](https://docs.apify.com/cli/) and your own Apify
account — none of this can be done from the deal-sourcing agent's sandbox,
which has no network access to `apify.com` at all.

```bash
npm install -g apify-cli
apify login
cd apify-actors/au-broker-listing-crawler
apify push
```

That builds and deploys the actor to your account. Note the **actor ID**
it's given (`your-username~au-broker-listing-crawler`) — you'll need it both
for manual testing and for wiring it into the deal-sourcing agent.

## Configure it per site

Run it once per site from the Apify Console (or `apify call`), with a small
`maxItems` (5–10) as a first test. Starting points for the sites you named —
**these are homepage-level guesses, not verified listing-page URLs**: open
each site yourself, find its actual "browse all businesses for sale" page,
and put *that* URL in `startUrls` instead for real coverage.

| Site | Starting `startUrls` (verify/replace before real use) |
|---|---|
| BusinessForSale.com.au | `https://www.businessforsale.com.au` |
| Bsale | `https://www.bsale.com.au` |
| AnyBusiness | `https://www.anybusiness.com.au` |
| AllBusiness.com.au | `https://www.allbusiness.com.au` |
| LINK Business Brokers | `https://linkbusiness.com.au` |
| SBX Business Brokers | `https://www.sbxbusiness.com.au` |
| Resolve Marketplace | `https://www.resolve.com.au` |
| Benchmark Business | `https://www.benchmarkbusiness.com.au` |
| BusinessesForSale.com (Australia) | `https://www.businessesforsale.com/australia` |
| Franchise2Sell | `https://www.franchise2sell.com.au` |
| scaling.com.au | `https://scaling.com.au` |
| scalingup.com.au | `https://scalingup.com.au` |

For each site, after a first run:

- If it found real listings (check the Output tab), you're done — note
  the `startUrls` you used.
- If it found 0 items or clearly wrong pages, open the site in your
  browser's dev tools, find the repeating listing-card element, and set
  **`itemSelector`** to its CSS class (e.g. `.listing-card`) for direct,
  precise list-page extraction — or find a substring common to every
  listing URL (e.g. `/listing/`) and set **`itemLinkPattern`** to it.

## Wire a working config into the deal-sourcing agent

Once you have a real actor ID and a working `startUrls`/`itemSelector` per
site, send them back and they get added to `app/actors.py`'s
`ACTOR_REGISTRY` — twelve entries reusing the **same** actor ID with
different `input`, exactly like the existing `apify~website-content-crawler`
entries already do. Only `APIFY_TOKEN` is then needed to drive them (per the
project's live-sync docs) — no per-site env vars required.

## Cost and politeness

- `maxConcurrency` defaults to 2 and every request has a small randomised
  delay — deliberately low-load, not a fast scraper.
- `respectRobotsTxt` defaults to `true` and is enforced per-request (fetches
  `robots.txt` once per run, skips disallowed paths — verified in testing).
- `renderJs` (headless browser) defaults to **off**. Only turn it on for a
  site that genuinely needs JS to render listings — it costs meaningfully
  more Apify compute credit per page, and this project already ran a whole
  monthly credit allowance dry once.
- Keep `maxItems` and `maxCrawlPages` modest, and test each site manually
  before adding it to a daily scheduled sync.
