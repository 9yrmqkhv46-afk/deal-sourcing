/**
 * AU Broker Listing Crawler
 * ---------------------------------------------------------------------------
 * One generic, input-configured Apify actor that serves every AU business
 * broker / business-for-sale site, instead of one bespoke actor per site.
 * Everything site-specific (startUrls, an optional detail-link pattern, an
 * optional CSS selector for list-page cards) comes from the actor's INPUT,
 * so a single deployed actor is reused for every site by giving it a
 * different input per run (see the deal-sourcing agent's
 * APIFY_ACTOR_INPUT_<SOURCE_KEY> env-var override mechanism).
 *
 * Output fields are deliberately named to match the deal-sourcing agent's
 * existing tolerant field-probing (title/description/askingPrice/location),
 * so no changes are needed on the consuming side.
 *
 * No CSS selectors are hard-coded for any specific site: we don't have
 * network access to inspect real broker-site markup while writing this, so
 * extraction leans on things that are unusually stable across sites -
 * JSON-LD, Open Graph meta tags, <h1>, and regex heuristics for AUD prices
 * and Australian state abbreviations - plus an optional itemSelector /
 * itemLinkPattern override once a human has actually looked at the page.
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
    renderJs = false,
    respectRobotsTxt = true,
    maxConcurrency = 2,
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
    for (const name of ['og:title', 'og:description', 'og:price:amount', 'og:price:currency', 'description']) {
        const v = get(name);
        if (v) meta[name] = v;
    }
    return meta;
}

function extractPrice(text) {
    const m = (text || '').match(/(?:AUD?\s*)?\$\s?\d[\d,]*(?:\.\d+)?\s?(?:k|K|m|M)?/);
    return m ? m[0].trim() : null;
}

function extractLocation(text) {
    // Prefer "City, STATE" (comma required) - a bare "Word Word STATE" pattern
    // false-positives too easily on titles like "Packaging Manufacturer VIC".
    const withCity = (text || '').match(/\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),\s?(NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\b/);
    if (withCity) return withCity[0].trim();
    const bare = (text || '').match(/\b(NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\b/);
    return bare ? bare[0].trim() : null;
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

function extractDetailRecord($, url) {
    const bodyText = cleanText($('body').text(), 6000);
    const jsonLd = extractJsonLd($);
    const meta = extractMeta($);

    const title =
        cleanText($('h1').first().text()) ||
        meta['og:title'] ||
        cleanText($('title').first().text()) ||
        null;

    const description =
        meta['og:description'] ||
        meta['description'] ||
        cleanText($('p').first().text(), 800) ||
        null;

    return {
        url,
        title,
        description: description ? cleanText(description, 800) : null,
        askingPrice: meta['og:price:amount'] || extractPrice(bodyText),
        location: extractLocation(bodyText),
        jsonLd: jsonLd.length ? jsonLd : undefined,
        raw_text: bodyText,
    };
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
            const record = {
                url: absUrl,
                title: cleanText(card.find('h1,h2,h3,h4,a').first().text()) || null,
                description: cardText.slice(0, 500) || null,
                askingPrice: extractPrice(cardText),
                location: extractLocation(cardText),
                raw_text: cardText,
            };
            if (record.title || record.askingPrice) {
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
            const record = {
                url: absUrl,
                title: cleanText(el.text()) || null,
                description: context.slice(0, 500) || null,
                askingPrice: extractPrice(context),
                location: extractLocation(context),
                raw_text: context,
            };
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

const CrawlerClass = renderJs ? PlaywrightCrawler : CheerioCrawler;

const crawler = new CrawlerClass({
    maxRequestsPerCrawl: maxCrawlPages,
    maxConcurrency,
    requestHandlerTimeoutSecs: 60,
    async requestHandler(context) {
        const { request, enqueueLinks, log } = context;
        if (itemsPushed >= maxItems) return;

        // Small, randomised delay - be a polite, low-load crawler.
        await sleep(400 + Math.random() * 500);

        if (!(await isAllowed(request.url))) {
            log.info(`Skipping ${request.url} - disallowed by robots.txt`);
            return;
        }

        const $ = renderJs ? await context.parseWithCheerio() : context.$;
        const label = request.userData?.label;

        if (label === 'DETAIL') {
            const record = extractDetailRecord($, request.loadedUrl || request.url);
            if (record.title || record.description || record.askingPrice) {
                await Dataset.pushData(record);
                itemsPushed += 1;
            }
            return;
        }

        await handleListPage($, request, enqueueLinks, log);
    },
    failedRequestHandler({ request, log }, error) {
        log.warning(`Request failed permanently: ${request.url} (${error?.message || 'unknown error'})`);
    },
});

await crawler.run(startUrls.map((u) => ({ url: typeof u === 'string' ? u : u.url })));

log.info(`Done. Pushed ${itemsPushed} item(s) to the dataset.`);
await Actor.exit();
