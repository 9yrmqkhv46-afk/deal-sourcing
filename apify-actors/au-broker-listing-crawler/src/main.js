/**
 * AU Broker Listing Crawler
 * ---------------------------------------------------------------------------
 * One generic, input-configured Apify actor that serves every AU business
 * broker / business-for-sale / liquidator-notice site, instead of one
 * bespoke actor per site. Everything site-specific (startUrls, an optional
 * detail-link pattern, an optional CSS selector for list-page cards, and the
 * crawler engine to use) comes from the actor's INPUT, so a single deployed
 * actor is reused for every site by giving it a different input per run.
 *
 * Output field names are chosen to match the deal-sourcing agent's actual
 * structured-extraction vocabulary (app/handlers.py's RawFields), NOT just
 * its lenient fallback text-blob prober - asking_price/revenue/ebitda are
 * emitted as real NUMBERS (or a [low, high] range) rather than formatted
 * strings, and location_text/listing_date use the exact keys the pipeline
 * reads. A formatted-string/back-compat alias (askingPrice, location) is
 * also included for the lenient blob prober, but the numeric/exact-key
 * fields are what actually populate a Deal's financials.
 *
 * No CSS selectors are hard-coded for any specific site: this project has no
 * network access to inspect real broker-site markup while writing this, so
 * extraction leans on things that are unusually stable across independently
 * built sites - JSON-LD, Open Graph meta tags, <h1>, and regex heuristics
 * for AUD amounts and Australian state abbreviations - plus an optional
 * itemSelector / itemLinkPattern override once a human has actually looked
 * at the page.
 */

import { Actor, log } from 'apify';
import { CheerioCrawler, PlaywrightCrawler, Dataset } from 'crawlee';

await Actor.init();

const input = (await Actor.getInput()) ?? {};
const {
    startUrls = [],
    itemLinkPattern = '',
    itemSelector = '',
    followDetailPages = true,
    maxItems = 50,
    maxCrawlPages = 120,
    // crawlerMode: "cheerio" (default, cheap) | "playwright" (JS render) |
    // "playwright-stealth" (JS render + anti-bot-detection plugin, for
    // Cloudflare/PerimeterX-protected sites). `renderJs: true` is kept as a
    // back-compat alias for crawlerMode: "playwright".
    crawlerMode = input.renderJs ? 'playwright' : 'cheerio',
    respectRobotsTxt = true,
    maxConcurrency = 2,
    // Apify Proxy. useApifyProxy=true + proxyGroups=["RESIDENTIAL"] is the
    // usual combination for a site with real anti-bot protection - note
    // this costs meaningfully more and RESIDENTIAL proxy access may not be
    // included on every Apify plan; verify in your account before relying
    // on it.
    useApifyProxy = false,
    proxyGroups = [],
} = input;

if (!startUrls.length) {
    throw new Error('No startUrls provided - configure at least one listing/search page URL.');
}

const USER_AGENT = 'Mozilla/5.0 (compatible; AU-Broker-Listing-Crawler/1.0; contact: set-your-contact-here)';

let itemsPushed = 0;
const robotsCache = new Map(); // origin -> { disallow: string[] }

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function absolutize(href, base) {
    try {
        return new URL(href, base).toString();
    } catch {
        return null;
    }
}

function parseRobots(text) {
    const lines = text.split(/\r?\n/);
    let inStarGroup = false;
    const disallow = [];
    for (const rawLine of lines) {
        const line = rawLine.split('#')[0].trim();
        if (!line) continue;
        const sep = line.indexOf(':');
        if (sep === -1) continue;
        const key = line.slice(0, sep).trim().toLowerCase();
        const value = line.slice(sep + 1).trim();
        if (key === 'user-agent') {
            inStarGroup = value === '*';
        } else if (key === 'disallow' && inStarGroup && value) {
            disallow.push(value);
        }
    }
    return { disallow };
}

async function fetchRobots(origin) {
    if (robotsCache.has(origin)) return robotsCache.get(origin);
    let rules = { disallow: [] };
    try {
        const res = await fetch(`${origin}/robots.txt`, { headers: { 'User-Agent': USER_AGENT } });
        if (res.ok) rules = parseRobots(await res.text());
    } catch {
        // No robots.txt, or it failed to load - treat as unrestricted.
    }
    robotsCache.set(origin, rules);
    return rules;
}

async function isAllowed(url) {
    if (!respectRobotsTxt) return true;
    try {
        const u = new URL(url);
        const rules = await fetchRobots(u.origin);
        return !rules.disallow.some((rule) => u.pathname.startsWith(rule));
    } catch {
        return true;
    }
}

function cleanText(raw, maxLen) {
    const text = (raw || '').replace(/\s+/g, ' ').trim();
    return maxLen ? text.slice(0, maxLen) : text;
}

function extractJsonLd($) {
    const blocks = [];
    $('script[type="application/ld+json"]').each((_, el) => {
        try {
            blocks.push(JSON.parse($(el).contents().text()));
        } catch {
            // Malformed JSON-LD - skip it, never let it crash the crawl.
        }
    });
    return blocks;
}

function extractMeta($) {
    const meta = {};
    const get = (name) => $(`meta[property="${name}"], meta[name="${name}"]`).attr('content');
    for (const name of [
        'og:title', 'og:description', 'og:price:amount', 'og:price:currency',
        'description', 'article:published_time',
    ]) {
        const v = get(name);
        if (v) meta[name] = v;
    }
    return meta;
}

/* ------------------------- amount parsing -------------------------------
 * The pipeline these records feed only trusts NUMERIC asking_price/revenue/
 * ebitda (or a [low, high] range - it auto-midpoints and flags ESTIMATED).
 * A formatted string like "$1,250,000" is never parsed downstream, so it
 * must be converted to a real number here or the figure is silently lost. */

function parseAmountToken(token) {
    if (!token) return null;
    const m = String(token).match(/\$?\s?(\d[\d,]*(?:\.\d+)?)\s?(k|K|m|M)?/);
    if (!m) return null;
    let value = parseFloat(m[1].replace(/,/g, ''));
    if (!Number.isFinite(value)) return null;
    const suffix = (m[2] || '').toLowerCase();
    if (suffix === 'k') value *= 1_000;
    if (suffix === 'm') value *= 1_000_000;
    return value;
}

function extractAmount(text) {
    const m = (text || '').match(/\$\s?\d[\d,]*(?:\.\d+)?\s?(?:k|K|m|M)?/);
    return m ? m[0].trim() : null;
}

function extractAmountRange(text) {
    const m = (text || '').match(
        /\$\s?\d[\d,.]*\s?(?:k|K|m|M)?\s?(?:-|to|–)\s?\$\s?\d[\d,.]*\s?(?:k|K|m|M)?/,
    );
    if (!m) return null;
    const parts = m[0].split(/-|to|–/);
    if (parts.length !== 2) return null;
    const low = parseAmountToken(parts[0]);
    const high = parseAmountToken(parts[1]);
    if (low == null || high == null) return null;
    return [low, high];
}

/** Numeric asking price (or [low, high] range), or null - never fabricated. */
function extractAskingPriceValue(text) {
    const labeled = extractLabeledAmount(text, ['asking price', 'price guide', 'price']);
    if (labeled != null) return labeled;
    const range = extractAmountRange(text);
    if (range) return range;
    return parseAmountToken(extractAmount(text));
}

/** Find "<label>[:/-] $amount" (case-insensitive); null if the label never appears. */
function extractLabeledAmount(text, labels) {
    if (!text) return null;
    const alt = labels.map((l) => l.replace(/\s+/g, '\\s*')).join('|');
    const re = new RegExp(`(?:${alt})\\s*[:\\-]?\\s*(\\$\\s?\\d[\\d,]*(?:\\.\\d+)?\\s?(?:k|K|m|M)?)`, 'i');
    const m = text.match(re);
    return m ? parseAmountToken(m[1]) : null;
}

function extractLocationText(text) {
    // Prefer "City, STATE" (comma required) - a bare "Word Word STATE" pattern
    // false-positives too easily on titles like "Packaging Manufacturer VIC".
    const withCity = (text || '').match(/\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),\s?(NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\b/);
    if (withCity) return withCity[0].trim();
    const bare = (text || '').match(/\b(NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\b/);
    return bare ? bare[0].trim() : null;
}

function extractStateCode(text) {
    const m = (text || '').match(/\b(NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\b/);
    return m ? m[0] : null;
}

function extractListingDate(jsonLd, meta) {
    for (const block of jsonLd) {
        const d = block?.datePublished || block?.dateCreated || block?.offers?.availabilityStarts;
        if (d) return String(d).slice(0, 10);
    }
    if (meta['article:published_time']) return String(meta['article:published_time']).slice(0, 10);
    return null;
}

/** Best-effort broker/agent contact from JSON-LD (Person/Organization) - omit, never guess, if absent. */
function extractBrokerContact(jsonLd, text) {
    for (const block of jsonLd) {
        const seller = block?.seller || block?.offers?.seller || block?.agent;
        if (seller?.name) {
            return {
                person_or_org_name: seller.name,
                role_or_title: 'Broker',
                email: seller.email || undefined,
                phone: seller.telephone || undefined,
            };
        }
    }
    const m = (text || '').match(/\b(?:agent|broker|listed by|contact)\s*[:\-]?\s*([A-Z][a-zA-Z'\-]+(?:\s[A-Z][a-zA-Z'\-]+){1,2})/i);
    if (m) return { person_or_org_name: m[1].trim(), role_or_title: 'Broker' };
    return null;
}

function looksLikeDetailLink(href, text, pattern) {
    if (!href) return false;
    if (pattern) return href.includes(pattern);
    const skip = /(login|signin|signup|register|^mailto:|^tel:|contact|about-us|privacy|terms|cart|checkout|account|wp-admin|#$)/i;
    if (skip.test(href)) return false;
    const t = (text || '').trim();
    const hasWordyText = t.length >= 8 && t.length <= 140;
    const hasSlugShape = /\d/.test(href) || (href.match(/-/g) || []).length >= 2;
    return hasWordyText || hasSlugShape;
}

/** Build the pipeline-aligned record shared by both list- and detail-page extraction. */
function buildRecord({ url, title, descriptionCandidate, bodyText, jsonLd = [], meta = {} }) {
    const description = descriptionCandidate ? cleanText(descriptionCandidate, 800) : null;
    const askingPriceValue = extractAskingPriceValue(bodyText);
    const askingPriceText = extractAmount(bodyText);
    const revenue = extractLabeledAmount(bodyText, ['revenue', 'turnover', 'annual revenue']);
    const ebitda = extractLabeledAmount(bodyText, ['ebitda', 'net profit', 'cash\\s*flow', 'sde']);
    const locationText = extractLocationText(bodyText);
    const state = extractStateCode(bodyText);
    const listingDate = extractListingDate(jsonLd, meta);
    const broker = extractBrokerContact(jsonLd, bodyText);

    const record = {
        url,
        title: title || null,
        description,
        // --- exact keys the pipeline's handlers.py actually reads ---
        location_text: locationText,
        state: state || undefined, // picked up as company.state via the flat-struct fallback
        asking_price: askingPriceValue,
        asking_price_currency: askingPriceValue != null ? 'AUD' : undefined,
        revenue: revenue ?? undefined,
        revenue_currency: revenue != null ? 'AUD' : undefined,
        ebitda: ebitda ?? undefined,
        ebitda_currency: ebitda != null ? 'AUD' : undefined,
        listing_date: listingDate || undefined,
        contacts: broker ? [broker] : undefined,
        // --- back-compat / lenient-blob-prober aliases ---
        location: locationText,
        askingPrice: askingPriceText,
        jsonLd: jsonLd.length ? jsonLd : undefined,
        raw_text: bodyText,
    };
    // Drop undefined keys so the pushed record stays clean.
    return Object.fromEntries(Object.entries(record).filter(([, v]) => v !== undefined));
}

function extractDetailRecord($, url) {
    const bodyText = cleanText($('body').text(), 6000);
    const jsonLd = extractJsonLd($);
    const meta = extractMeta($);

    const title =
        cleanText($('h1').first().text()) ||
        meta['og:title'] ||
        cleanText($('title').first().text()) ||
        null;

    const descriptionCandidate = meta['og:description'] || meta['description'] || cleanText($('p').first().text(), 800);

    return buildRecord({ url, title, descriptionCandidate, bodyText, jsonLd, meta });
}

async function handleListPage($, request, enqueueLinks, log) {
    const base = request.loadedUrl || request.url;

    if (itemSelector) {
        const cards = $(itemSelector);
        for (let i = 0; i < cards.length && itemsPushed < maxItems; i += 1) {
            const card = cards.eq(i);
            const href = card.find('a[href]').first().attr('href');
            const absUrl = (href && absolutize(href, base)) || base;
            const cardText = cleanText(card.text(), 2000);
            const title = cleanText(card.find('h1,h2,h3,h4,a').first().text()) || null;
            const record = buildRecord({ url: absUrl, title, descriptionCandidate: cardText, bodyText: cardText });
            if (record.title || record.asking_price != null || record.askingPrice) {
                await Dataset.pushData(record);
                itemsPushed += 1;
            }
        }
        return;
    }

    // No itemSelector: discover candidate detail links generically.
    const seen = new Set();
    const candidates = [];
    $('a[href]').each((_, el) => {
        const $el = $(el);
        const href = $el.attr('href');
        const text = $el.text();
        if (!looksLikeDetailLink(href, text, itemLinkPattern)) return;
        const absUrl = absolutize(href, base);
        if (absUrl && !seen.has(absUrl)) {
            seen.add(absUrl);
            candidates.push({ el: $el, absUrl });
        }
    });

    if (!followDetailPages) {
        // Thin extraction straight from the list page - no extra requests.
        for (const { el, absUrl } of candidates) {
            if (itemsPushed >= maxItems) break;
            const context = cleanText(el.closest('li,div,article,tr').first().text() || el.text(), 1500);
            const record = buildRecord({ url: absUrl, title: cleanText(el.text()) || null, descriptionCandidate: context, bodyText: context });
            await Dataset.pushData(record);
            itemsPushed += 1;
        }
        return;
    }

    const remaining = Math.max(0, maxItems - itemsPushed);
    const urls = candidates.slice(0, remaining).map((c) => c.absUrl);
    if (urls.length) {
        log.info(`Enqueuing ${urls.length} detail page(s) from ${base}`);
        await enqueueLinks({ urls, userData: { label: 'DETAIL' } });
    }
}

/* ------------------------- crawler engine selection ----------------------
 * "cheerio": fast, cheap, no browser - the default for plain HTML sites.
 * "playwright": renders JS, needed when listings only appear after
 *   client-side rendering.
 * "playwright-stealth": playwright-extra + the puppeteer-extra stealth
 *   plugin (a documented, valid combination - the stealth plugin ecosystem
 *   is shared across puppeteer-extra and playwright-extra), for sites
 *   behind Cloudflare/PerimeterX-style bot detection. This is inherently
 *   best-effort and adversarial by nature - it was NOT verified against a
 *   real protected site (this project has no network access to one); treat
 *   the first run as a test. */

let crawlerOptions = {
    maxRequestsPerCrawl: maxCrawlPages,
    maxConcurrency,
    requestHandlerTimeoutSecs: 60,
    failedRequestHandler({ request, log: reqLog }, error) {
        reqLog.warning(`Request failed permanently: ${request.url} (${error?.message || 'unknown error'})`);
    },
};

if (useApifyProxy) {
    crawlerOptions.proxyConfiguration = await Actor.createProxyConfiguration(
        proxyGroups.length ? { groups: proxyGroups } : undefined,
    );
}

// Local development only: override the Chromium binary Playwright launches
// when testing outside Apify's own Docker image (which already ships a
// version-matched Playwright + Chromium pair, so this is a no-op there).
const localChromiumPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
if (localChromiumPath) {
    crawlerOptions.launchContext = { launchOptions: { executablePath: localChromiumPath } };
}

const sharedRequestHandler = async (context) => {
    const { request, enqueueLinks, log: reqLog } = context;
    if (itemsPushed >= maxItems) return;

    // Small, randomised delay - be a polite, low-load crawler.
    await sleep(400 + Math.random() * 500);

    if (!(await isAllowed(request.url))) {
        reqLog.info(`Skipping ${request.url} - disallowed by robots.txt`);
        return;
    }

    const $ = context.$ ?? (await context.parseWithCheerio());
    const label = request.userData?.label;

    if (label === 'DETAIL') {
        const record = extractDetailRecord($, request.loadedUrl || request.url);
        if (record.title || record.description || record.asking_price != null || record.askingPrice) {
            await Dataset.pushData(record);
            itemsPushed += 1;
        }
        return;
    }

    await handleListPage($, request, enqueueLinks, reqLog);
};

let crawler;

if (crawlerMode === 'playwright-stealth') {
    let chromiumExtra;
    try {
        const { chromium } = await import('playwright-extra');
        const stealth = (await import('puppeteer-extra-plugin-stealth')).default;
        chromium.use(stealth());
        chromiumExtra = chromium;
    } catch (err) {
        log.warning(
            `playwright-extra / puppeteer-extra-plugin-stealth not available (${err?.message}); ` +
            'add them to package.json and rebuild. Falling back to plain Playwright.',
        );
    }
    crawlerOptions = {
        ...crawlerOptions,
        launchContext: {
            ...crawlerOptions.launchContext,
            ...(chromiumExtra ? { launcher: chromiumExtra } : {}),
        },
        requestHandler: sharedRequestHandler,
    };
    crawler = new PlaywrightCrawler(crawlerOptions);
} else if (crawlerMode === 'playwright') {
    crawler = new PlaywrightCrawler({ ...crawlerOptions, requestHandler: sharedRequestHandler });
} else {
    crawler = new CheerioCrawler({ ...crawlerOptions, requestHandler: sharedRequestHandler });
}

await crawler.run(startUrls.map((u) => ({ url: typeof u === 'string' ? u : u.url })));

log.info(`Done. Pushed ${itemsPushed} item(s) to the dataset. (crawlerMode=${crawlerMode})`);
await Actor.exit();
