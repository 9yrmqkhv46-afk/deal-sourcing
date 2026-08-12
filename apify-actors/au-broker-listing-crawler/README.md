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

Each pushed dataset record uses the **exact keys the deal-sourcing agent's
pipeline actually reads** (`app/handlers.py`'s `RawFields`), with numeric
`asking_price`/`revenue`/`ebitda` — not formatted strings. This was a real
bug in the first version of this actor: it emitted `askingPrice` as a string
like `"$1,250,000"` and `location` instead of `location_text`, and the
pipeline's financial-figure extraction *only* trusts already-numeric
structured fields (per `handlers.py`'s own docstring, it deliberately never
parses money out of free text) — so a perfectly successful scrape would
still have shown up with `asking_price: null` downstream. Fixed now;
verified locally that a Deal's numeric fields actually populate.

```json
{
  "url": "https://example.com/listing/...",
  "title": "Established Packaging Manufacturer - VIC",
  "description": "Profitable packaging business...",
  "location_text": "Melbourne, VIC",
  "state": "VIC",
  "asking_price": 1250000,
  "asking_price_currency": "AUD",
  "revenue": 2400000,
  "revenue_currency": "AUD",
  "ebitda": 480000,
  "ebitda_currency": "AUD",
  "listing_date": "2026-06-01",
  "contacts": [ { "person_or_org_name": "Sarah Whitman", "role_or_title": "Broker" } ],
  "location": "Melbourne, VIC",
  "askingPrice": "$1,250,000",
  "jsonLd": [ { "...": "..." } ],
  "raw_text": "full extracted page text, for the pipeline's own extraction"
}
```

`revenue`/`ebitda`/`listing_date`/`contacts` are genuinely best-effort and
often absent (most listings don't publish exact financials openly) —
consistent with the pipeline's own "never fabricate, null over guess"
philosophy. `location`/`askingPrice` (string) are kept as back-compat
aliases for the pipeline's separate lenient text-blob prober; they aren't
what actually populates a Deal's financials.

## Crawler engine (`crawlerMode`)

| Mode | Cost | When to use |
|---|---|---|
| `cheerio` (default) | Cheap | Plain server-rendered HTML — most of these sites |
| `playwright` | Moderate | Listings only appear after client-side JS rendering |
| `playwright-stealth` | Highest | Site is behind Cloudflare/PerimeterX-style bot detection |

`playwright-stealth` uses `playwright-extra` + the `puppeteer-extra-plugin-stealth`
plugin (a documented, valid combination — the stealth plugin ecosystem is
shared across puppeteer-extra and playwright-extra). This was verified to
run without crashing against a plain test site, but **anti-bot bypass is
inherently adversarial and was never tested against a real protected site**
(no network access to one from this project's sandbox) — treat the first
real run as a test, and consider pairing it with `useApifyProxy: true` +
`proxyGroups: ["RESIDENTIAL"]` if the site still blocks it. Verify your
Apify plan actually includes residential proxy access/cost before relying
on that combination for a daily sync.

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
`maxItems` (5–10) as a first test. Starting points below are
**homepage/section-level guesses, not verified listing-page URLs or
selectors** — this project has no network access to confirm any of them.
Open each site yourself, find its actual "browse all listings" page, and
refine `startUrls` (and `itemSelector`/`itemLinkPattern` if the generic
heuristic doesn't find real listings) before relying on it.

### Business broking marketplaces (free/public, no login)

| Site | Starting `startUrls` | `crawlerMode` |
|---|---|---|
| Seek Business | `https://www.seekbusiness.com.au` | `playwright-stealth` — flagged as Cloudflare/PerimeterX-protected |
| AnyBusiness | `https://www.anybusiness.com.au` | `cheerio` |
| BusinessesForSale Australia | `https://australia.businessesforsale.com` | `cheerio` |
| CommercialRealEstate.com.au (business portal) | `https://www.commercialrealestate.com.au/business-for-sale` | `playwright-stealth` — flagged as Cloudflare/PerimeterX-protected |
| Bsale | `https://www.bsale.com.au` | `cheerio` |
| Business2Sell | `https://www.business2sell.com.au` | `cheerio` |
| BusinessSales.com.au | `https://app.businesssales.com.au` | `cheerio`; try `playwright` if 0 items (an `app.` subdomain often means a JS-rendered app) |
| LINK Business Brokers | `https://www.linkbusiness.com.au` | `cheerio` |
| The Finn Group | `https://www.thefinngroup.com.au` | `cheerio` |
| DealStream Australia | `https://dealstream.com/australia-businesses-for-sale` | `cheerio` |

### Liquidator / distressed-asset channels (free/public)

| Site | Starting `startUrls` | `crawlerMode` | Notes |
|---|---|---|---|
| ASIC Published Notices | `https://publishednotices.asic.gov.au` | `cheerio` | ASP.NET site — if the real search is a POST-form submission (not a plain browsable list), the generic actor won't reach results; it'll likely need a small bespoke follow-up (Playwright filling/submitting the search form) once you've looked at it |
| AFSA / National Personal Insolvency Index | `https://www.afsa.gov.au` | `cheerio` | You gave a name, not a URL — find the actual NPII search-results page first |
| McGrathNicol Deals | `https://www.mcgrathnicol.com/deals` | `cheerio` |
| KordaMentha Restructuring | `https://www.kordamentha.com` | `cheerio` | Homepage only — find their actual "assets for sale" section |
| BRI Ferrier Insolvency Listings | `https://www.briferrier.com.au` | `cheerio` |
| FTI Consulting Australia | `https://www.fticonsulting.com/au` | `cheerio` | Domain guessed — verify |
| RSM Australia | `https://www.rsm.global/australia` | `cheerio` | Domain guessed — verify |
| Grays | `https://www.grays.com` | `playwright` — likely a JS-heavy auction-listing app; try `cheerio` first, it's cheaper |
| Pickles Auctions | `https://www.pickles.com.au` | `playwright` — same reasoning as Grays |
| Lloyds Auctions | `https://www.lloydsauctions.com.au` | `playwright` — same reasoning as Grays |

For each site, after a first run:

- If it found real listings (check the Output tab), you're done — note
  the `startUrls` you used.
- If it found 0 items or clearly wrong pages, open the site in your
  browser's dev tools, find the repeating listing-card element, and set
  **`itemSelector`** to its CSS class (e.g. `.listing-card`) for direct,
  precise list-page extraction — or find a substring common to every
  listing URL (e.g. `/listing/`) and set **`itemLinkPattern`** to it.

## Wire a working config into the deal-sourcing agent

Once you have a real actor ID and a working `startUrls`/`itemSelector`/
`crawlerMode` per site, send them back and they get added to
`app/actors.py`'s `ACTOR_REGISTRY` — one entry per site, all reusing the
**same** actor ID with different `input`, exactly like the existing
`apify~website-content-crawler` entries already do. Only `APIFY_TOKEN` is
then needed to drive them (per the project's live-sync docs) — no per-site
env vars required.

## Cost and politeness

- `maxConcurrency` defaults to 2 and every request has a small randomised
  delay — deliberately low-load, not a fast scraper.
- `respectRobotsTxt` defaults to `true` and is enforced per-request (fetches
  `robots.txt` once per run, skips disallowed paths — verified in testing).
- `crawlerMode` defaults to `cheerio` (cheapest). Only step up to
  `playwright` or `playwright-stealth` for a site that actually needs it —
  each step costs meaningfully more Apify compute credit per page, and this
  project already ran a whole monthly credit allowance dry once already.
- Keep `maxItems` and `maxCrawlPages` modest, and test each site manually
  before adding it to a daily scheduled sync.
