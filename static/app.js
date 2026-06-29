"use strict";

/* =========================================================================
 * TransformBiz dashboard — vanilla JS, no build step, no external deps.
 * Talks to GET /api/sample and POST /api/process.
 * ========================================================================= */

const state = {
  data: null,
  lastBatch: null,
  tab: "deals",
  sort: { key: "overall_score", dir: "desc" },
  filters: {
    search: "",
    classification: "all",
    source: "all",
    sector: "all",
    minScore: 0,
    franchiseOnly: false,
    hideStale: false,
  },
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const CLASS_META = {
  core_thesis: { label: "Core", klass: "core" },
  adjacent_thesis: { label: "Adjacent", klass: "adjacent" },
  reject: { label: "Reject", klass: "reject" },
};

/* ---------------------------- utilities -------------------------------- */

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* "View on original site" external link, or "" when no URL is available. */
function originalSiteLink(url, label) {
  if (!url) return "";
  return `<a class="link link-external" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label || "View on original site")} ↗</a>`;
}

function fmtMoney(amount, currency, estimated) {
  if (amount == null) return "—";
  const n = Number(amount).toLocaleString("en-AU", { maximumFractionDigits: 0 });
  const cur = currency ? currency + " " : "";
  const est = estimated ? ' <span class="est-tag">EST</span>' : "";
  return `${cur}$${n}${est}`;
}

function titleCase(str) {
  if (!str) return "";
  return String(str).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function companyOf(companyId) {
  if (!state.data) return null;
  return (state.data.companies || []).find((c) => c.company_id === companyId) || null;
}

function showLoading(text) {
  $("#loading-text").textContent = text || "Processing…";
  $("#loading").hidden = false;
}
function hideLoading() { $("#loading").hidden = true; }

let toastTimer = null;
function toast(msg, kind) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (kind ? " " + kind : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}

/* ---------------------------- data loading ----------------------------- */

async function loadSample() {
  showLoading("Loading sample data…");
  try {
    const res = await fetch("/api/sample");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.lastBatch = data.batch;
    await processBatch(data.batch, { silent: true });
    toast("Sample data loaded — " + data.batch.length + " source items", "ok");
  } catch (err) {
    hideLoading();
    toast("Failed to load sample: " + err.message, "error");
  }
}

async function processBatch(batch, opts = {}) {
  showLoading("Processing " + batch.length + " source item(s)…");
  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ batch }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || "HTTP " + res.status);
    }
    state.data = await res.json();
    state.lastBatch = batch;
    buildFilterOptions();
    render();
    if (!opts.silent) toast("Processed " + state.data.deals.length + " deals", "ok");
    return true;
  } catch (err) {
    toast("Processing failed: " + err.message, "error");
    return false;
  } finally {
    hideLoading();
  }
}

/* ---------------------------- refresh + status ------------------------- */

function fmtSyncTime(iso) {
  if (!iso) return "never";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "never";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function renderStatus(meta) {
  if (!meta) return;
  const last = meta.last_synced_at;
  $("#last-synced").textContent = last
    ? "Last synced at " + fmtSyncTime(last)
    : "Last synced: never";

  const jobs = meta.jobs || [];
  const running = jobs.some((j) => j.status === "running");
  $("#sync-pulse").classList.toggle("live", running);

  $("#job-badges").innerHTML = jobs
    .map((j) => {
      const status = (j.status || "idle").toLowerCase();
      const name = j.source_key || j.job_name || "source";
      const count = j.item_count ? ` ${j.item_count}` : "";
      const title = [j.job_name, j.message, j.last_sync_at ? "last: " + j.last_sync_at : ""]
        .filter(Boolean).join(" — ");
      return `<span class="job-badge job-${status}" title="${escapeHtml(title)}">
        <span class="job-badge-dot"></span>${escapeHtml(name)}${escapeHtml(count)}</span>`;
    })
    .join("") || '<span class="job-badge job-idle"><span class="job-badge-dot"></span>no sources yet</span>';
}

async function refreshNow() {
  showLoading("Refreshing from latest synced data…");
  try {
    const res = await fetch("/api/refresh", { method: "POST" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const body = await res.json();
    // The refresh envelope contains the strict output keys + sync metadata.
    state.data = {
      deals: body.deals || [],
      companies: body.companies || [],
      founders: body.founders || [],
      contacts: body.contacts || [],
      summary: body.summary || {},
    };
    buildFilterOptions();
    render();
    renderStatus({ last_synced_at: body.last_synced_at, jobs: body.jobs });
    toast("Refreshed — " + state.data.deals.length + " deals from latest snapshot", "ok");
  } catch (err) {
    toast("Refresh failed: " + err.message, "error");
  } finally {
    hideLoading();
  }
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    renderStatus(await res.json());
  } catch (_err) {
    /* status polling is best-effort; ignore transient errors */
  }
}

/* ---------------------------- filter options --------------------------- */

function buildFilterOptions() {
  const deals = state.data.deals || [];
  const sources = Array.from(new Set(deals.map((d) => d.source_type))).sort();
  const sectors = Array.from(
    new Set(deals.map((d) => (companyOf(d.company_id) || {}).sector).filter(Boolean))
  ).sort();

  const srcSel = $("#f-source");
  srcSel.innerHTML = '<option value="all">All</option>' +
    sources.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(titleCase(s))}</option>`).join("");

  const secSel = $("#f-sector");
  secSel.innerHTML = '<option value="all">All</option>' +
    sectors.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(titleCase(s))}</option>`).join("");
}

/* ---------------------------- rendering -------------------------------- */

function render() {
  if (!state.data) return;
  const s = state.data.summary;
  $("#kpi-core").textContent = s.core_thesis_deal_count;
  $("#kpi-adjacent").textContent = s.adjacent_thesis_deal_count;
  $("#kpi-reject").textContent = s.reject_count;
  $("#kpi-total").textContent = state.data.deals.length;
  $("#kpi-contacts").textContent = (state.data.contacts || []).length;
  $("#kpi-row").hidden = false;

  renderDonut(s);
  $("#raw-json").textContent = JSON.stringify(state.data, null, 2);

  renderDeals();
  renderCompanies();
  renderFounders();
  renderContacts();
}

function renderDonut(s) {
  const core = s.core_thesis_deal_count;
  const adj = s.adjacent_thesis_deal_count;
  const rej = s.reject_count;
  const total = core + adj + rej || 1;
  const C = 2 * Math.PI * 15.9155; // circumference for r=15.9155 (=100/2π)
  const segs = [
    { v: core, color: "var(--core)", label: "Core" },
    { v: adj, color: "var(--adjacent)", label: "Adjacent" },
    { v: rej, color: "var(--reject)", label: "Reject" },
  ];
  let offset = 0;
  const circles = segs
    .map((seg) => {
      const frac = seg.v / total;
      const len = frac * C;
      const dash = `${len} ${C - len}`;
      const c = `<circle cx="18" cy="18" r="15.9155" fill="none" stroke="${seg.color}"
        stroke-width="5" stroke-dasharray="${dash}" stroke-dashoffset="${-offset}"
        transform="rotate(-90 18 18)"></circle>`;
      offset += len;
      return c;
    })
    .join("");
  $("#donut").innerHTML = `<svg viewBox="0 0 36 36" width="56" height="56">
    <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#eef2f7" stroke-width="5"></circle>
    ${circles}
    <text x="18" y="19.5" text-anchor="middle" font-size="8" font-weight="700" fill="#0f2742">${total}</text>
  </svg>`;
  $("#donut-legend").innerHTML = segs
    .map((seg) => `<span><i style="background:${seg.color}"></i>${seg.label} ${seg.v}</span>`)
    .join("");
}

function filteredDeals() {
  const f = state.filters;
  let deals = (state.data.deals || []).slice();
  deals = deals.filter((d) => {
    const co = companyOf(d.company_id) || {};
    if (f.classification !== "all" && d.thesis_match.classification !== f.classification) return false;
    if (f.source !== "all" && d.source_type !== f.source) return false;
    if (f.sector !== "all" && co.sector !== f.sector) return false;
    if (f.franchiseOnly && !d.is_franchise) return false;
    if (f.hideStale && d.is_stale) return false;
    if (d.thesis_match.overall_score < f.minScore) return false;
    if (f.search) {
      const hay = [d.title, co.name, co.sector, co.subsector, d.location_text]
        .filter(Boolean).join(" ").toLowerCase();
      if (!hay.includes(f.search.toLowerCase())) return false;
    }
    return true;
  });

  const { key, dir } = state.sort;
  const valOf = (d) => {
    const co = companyOf(d.company_id) || {};
    switch (key) {
      case "overall_score": return d.thesis_match.overall_score;
      case "classification": return d.thesis_match.classification;
      case "company": return (co.name || "").toLowerCase();
      case "sector": return (co.sector || "").toLowerCase();
      case "deal_size_bucket": return d.deal_size_bucket;
      default: return (d.title || "").toLowerCase();
    }
  };
  deals.sort((a, b) => {
    const av = valOf(a), bv = valOf(b);
    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return a.deal_id < b.deal_id ? -1 : 1;
  });
  return deals;
}

function filterDots(tm) {
  const items = [
    ["Sector", tm.passes_sector_filter],
    ["Age", tm.passes_age_filter],
    ["Financial", tm.passes_financial_filter],
    ["Founder", tm.passes_founder_filter],
    ["AI/automation", tm.ai_automation_potential_flag],
  ];
  return `<span class="dots">` + items
    .map(([label, v]) => {
      const cls = v === true ? "pass" : v === false ? "fail" : "unknown";
      const word = v === true ? "pass" : v === false ? "fail" : "unknown";
      return `<span class="dot ${cls}" title="${label}: ${word}" aria-label="${label}: ${word}"></span>`;
    })
    .join("") + `</span>`;
}

function scoreBar(tm) {
  const meta = CLASS_META[tm.classification] || CLASS_META.reject;
  const w = Math.max(6, tm.overall_score);
  return `<div class="score-cell"><div class="score-bar">
    <div class="score-fill ${meta.klass}" style="width:${w}%"></div>
    <span class="score-num">${tm.overall_score}</span>
  </div></div>`;
}

function classBadge(cls) {
  const meta = CLASS_META[cls] || { label: cls, klass: "reject" };
  return `<span class="badge badge-${meta.klass}">${meta.label}</span>`;
}

function renderDeals() {
  const deals = filteredDeals();
  const body = $("#deals-body");
  $("#result-count").textContent = deals.length + " of " + (state.data.deals || []).length + " deals";
  $("#deals-empty").hidden = deals.length > 0;

  body.innerHTML = deals
    .map((d) => {
      const co = companyOf(d.company_id) || {};
      const tm = d.thesis_match;
      const sector = co.sector
        ? escapeHtml(titleCase(co.sector)) + (co.subsector ? `<div class="cell-sub">${escapeHtml(titleCase(co.subsector))}</div>` : "")
        : '<span class="cell-sub">—</span>';
      const stale = d.is_stale ? '<span class="badge badge-stale">Stale</span>' : "";
      const fran = d.is_franchise ? '<span class="badge badge-franchise">Franchise</span>' : "";
      return `<tr tabindex="0" data-deal="${d.deal_id}">
        <td><div class="cell-title">${escapeHtml(d.title)} ${stale}</div>
            <div class="cell-sub">${fran}</div></td>
        <td>${escapeHtml(co.name || "—")}</td>
        <td>${sector}</td>
        <td class="nowrap"><span class="cell-sub">${escapeHtml(d.location_text || "—")}</span></td>
        <td><span class="badge badge-size">${escapeHtml(titleCase(d.deal_size_bucket))}</span></td>
        <td>${scoreBar(tm)}</td>
        <td>${classBadge(tm.classification)}</td>
        <td>${filterDots(tm)}</td>
        <td><span class="source-tag">${escapeHtml(titleCase(d.source_type))}</span>${d.listing_url ? `<div class="cell-sub">${originalSiteLink(d.listing_url, "Original site")}</div>` : ""}</td>
      </tr>`;
    })
    .join("");

  $$("#deals-body tr").forEach((tr) => {
    const open = () => openDrawer(tr.dataset.deal);
    tr.addEventListener("click", (e) => {
      // Let external "original site" links work without opening the drawer.
      if (e.target.closest("a")) return;
      open();
    });
    tr.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
  });

  $$("#deals-table th.sortable").forEach((th) => {
    th.onclick = () => {
      const key = th.dataset.sort;
      if (state.sort.key === key) {
        state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
      } else {
        state.sort.key = key;
        state.sort.dir = key === "overall_score" ? "desc" : "asc";
      }
      $$("#deals-table th.sortable").forEach((h) => h.classList.remove("active", "asc"));
      th.classList.add("active");
      if (state.sort.dir === "asc") th.classList.add("asc");
      renderDeals();
    };
  });
}

function renderCompanies() {
  const companies = state.data.companies || [];
  $("#companies-empty").hidden = companies.length > 0;
  $("#companies-grid").innerHTML = companies
    .map((c) => {
      const banned = c.banned_sector_flag ? '<span class="badge badge-reject">Excluded sector</span>' : "";
      const loc = [c.city, c.state, c.country].filter(Boolean).join(", ");
      const rows = [
        c.sector ? `<span><b>Sector</b> ${escapeHtml(titleCase(c.sector))}</span>` : "",
        c.founded_year ? `<span><b>Founded</b> ${c.founded_year}</span>` : "",
        c.age_years != null ? `<span><b>Age</b> ${c.age_years} yrs</span>` : "",
        c.employees != null ? `<span><b>Staff</b> ${c.employees}</span>` : "",
      ].filter(Boolean).join("");
      return `<div class="ecard">
        <div class="ecard-top"><span class="ecard-name">${escapeHtml(c.name)}</span>${banned}</div>
        <div class="ecard-meta">${escapeHtml(loc || "Location unknown")}</div>
        <div class="ecard-row">${rows || '<span class="cell-sub">Limited detail captured</span>'}</div>
      </div>`;
    })
    .join("");
}

function renderFounders() {
  const founders = state.data.founders || [];
  $("#founders-empty").hidden = founders.length > 0;
  $("#founders-grid").innerHTML = founders
    .map((f) => {
      const links = [
        f.linkedin_url ? `<a class="link" href="${escapeHtml(f.linkedin_url)}" target="_blank" rel="noopener">LinkedIn</a>` : "",
        f.email ? `<a class="link" href="mailto:${escapeHtml(f.email)}">Email</a>` : "",
        f.phone ? `<a class="link" href="tel:${escapeHtml(f.phone)}">${escapeHtml(f.phone)}</a>` : "",
      ].filter(Boolean).join("");
      const rows = [
        `<span><b>Role</b> ${escapeHtml(f.role)}</span>`,
        f.tenure_years != null ? `<span><b>Tenure</b> ${f.tenure_years} yrs</span>` : "",
        f.organization_name ? `<span><b>Org</b> ${escapeHtml(f.organization_name)}</span>` : "",
      ].filter(Boolean).join("");
      return `<div class="ecard">
        <div class="ecard-top"><span class="ecard-name">${escapeHtml(f.name)}</span></div>
        <div class="ecard-row">${rows}</div>
        ${links ? `<div class="ecard-links">${links}</div>` : ""}
      </div>`;
    })
    .join("");
}

function renderContacts() {
  const contacts = (state.data.summary && state.data.summary.top_contacts_for_outreach) || [];
  $("#contacts-empty").hidden = contacts.length > 0;
  $("#contacts-grid").innerHTML = contacts
    .map((c, i) => {
      const meta = [c.role_or_title, c.region_or_state].filter(Boolean).join(" · ");
      const links = [
        c.linkedin_url ? `<a class="link" href="${escapeHtml(c.linkedin_url)}" target="_blank" rel="noopener">LinkedIn</a>` : "",
        c.email ? `<a class="link" href="mailto:${escapeHtml(c.email)}">Email</a>` : "",
        c.phone ? `<a class="link" href="tel:${escapeHtml(c.phone)}">${escapeHtml(c.phone)}</a>` : "",
        originalSiteLink(c.portal_url_or_website || c.linkedin_url, "View on original site"),
      ].filter(Boolean).join("");
      const sector = c.sector_focus ? `<span><b>Focus</b> ${escapeHtml(c.sector_focus)}</span>` : "";
      const src = `<span><b>Source</b> ${escapeHtml(titleCase(c.source_type))} · ${escapeHtml(c.source_name)}</span>`;
      return `<div class="ecard">
        <div class="ecard-top"><span class="ecard-name">${escapeHtml(c.person_or_org_name)}</span>
          <span class="pill-rank">#${i + 1}</span></div>
        <div class="ecard-meta">${escapeHtml(meta || "Relationship lead")}</div>
        <div class="ecard-row">${sector}${src}</div>
        ${c.priority_reason ? `<div class="priority-banner"><b>Why prioritised:</b> ${escapeHtml(c.priority_reason)}</div>` : ""}
        ${links ? `<div class="ecard-links">${links}</div>` : ""}
      </div>`;
    })
    .join("");
}

/* ---------------------------- detail drawer ---------------------------- */

let lastFocused = null;

function fstate(v) {
  const word = v === true ? "Pass" : v === false ? "Fail" : "Unknown";
  const cls = v === true ? "pass" : v === false ? "fail" : "unknown";
  return `<span class="fstate ${cls}">${word}</span>`;
}

function openDrawer(dealId) {
  const d = (state.data.deals || []).find((x) => x.deal_id === dealId);
  if (!d) return;
  const co = companyOf(d.company_id) || {};
  const tm = d.thesis_match;

  const di = (k, v) => `<div class="d-item"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  const filters = [
    ["Sector", tm.passes_sector_filter],
    ["Trading age (6yr+)", tm.passes_age_filter],
    ["Financials in range", tm.passes_financial_filter],
    ["Founder tenure (20yr+)", tm.passes_founder_filter],
    ["AI / automation upside", tm.ai_automation_potential_flag],
  ];

  $("#drawer-title").textContent = d.title;
  $("#drawer-body").innerHTML = `
    <div class="d-section">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
        ${classBadge(tm.classification)}
        <span class="badge badge-size">${escapeHtml(titleCase(d.deal_size_bucket))}</span>
        ${d.is_franchise ? '<span class="badge badge-franchise">Franchise</span>' : ""}
        ${d.is_stale ? '<span class="badge badge-stale">Stale</span>' : ""}
        <span class="muted" style="margin-left:auto">Score <b style="color:var(--navy)">${tm.overall_score}</b>/100</span>
      </div>
      ${scoreBar(tm)}
    </div>

    <div class="d-section">
      <h3>Business</h3>
      <div class="d-grid">
        ${di("Company", escapeHtml(co.name || "—"))}
        ${di("Sector", escapeHtml(titleCase(co.sector) || "—") + (co.subsector ? " / " + escapeHtml(titleCase(co.subsector)) : ""))}
        ${di("Location", escapeHtml(d.location_text || "—"))}
        ${di("Deal type", escapeHtml(titleCase(d.deal_type)))}
        ${di("Founded", co.founded_year || "—")}
        ${di("Employees", co.employees != null ? co.employees : "—")}
      </div>
    </div>

    <div class="d-section">
      <h3>Financials</h3>
      <div class="d-grid">
        ${di("Asking price", fmtMoney(d.asking_price, d.asking_price_currency, d.asking_price_estimated))}
        ${di("Revenue", fmtMoney(d.revenue, d.revenue_currency, d.revenue_estimated))}
        ${di("EBITDA", fmtMoney(d.ebitda, d.ebitda_currency, d.ebitda_estimated))}
        ${di("Size bucket", escapeHtml(titleCase(d.deal_size_bucket)))}
      </div>
    </div>

    <div class="d-section">
      <h3>Recency</h3>
      <div class="d-grid">
        ${di("Listing date", escapeHtml(d.listing_date || "—"))}
        ${di("Last seen", escapeHtml(d.last_seen_at || "—"))}
      </div>
    </div>

    <div class="d-section">
      <h3>Thesis filters</h3>
      ${filters.map(([label, v]) => `<div class="filter-row"><span>${label}</span>${fstate(v)}</div>`).join("")}
    </div>

    <div class="d-section">
      <h3>Why this classification</h3>
      <p class="explain">${escapeHtml(tm.explanation)}</p>
    </div>

    ${d.competitive_notes ? `<div class="d-section"><h3>Competitive notes</h3><div class="d-note">${escapeHtml(d.competitive_notes)}</div></div>` : ""}
    ${d.ai_automation_potential_notes ? `<div class="d-section"><h3>AI / automation potential</h3><div class="d-note">${escapeHtml(d.ai_automation_potential_notes)}</div></div>` : ""}

    <div class="d-section">
      <h3>Provenance</h3>
      <div class="d-grid">
        ${di("Source", escapeHtml(titleCase(d.source_type)) + " · " + escapeHtml(d.source_name))}
        ${di("Reference", escapeHtml(d.external_listing_id_or_url))}
      </div>
      ${d.listing_url ? `<div class="d-section-links">${originalSiteLink(d.listing_url)}</div>` : ""}
    </div>

    ${d.raw_source_excerpt ? `<div class="d-section"><h3>Raw source excerpt</h3><div class="d-note d-excerpt">${escapeHtml(d.raw_source_excerpt)}</div></div>` : ""}
  `;

  lastFocused = document.activeElement;
  $("#drawer-overlay").hidden = false;
  $("#drawer").hidden = false;
  $("#drawer").focus();
}

function closeDrawer() {
  $("#drawer").hidden = true;
  $("#drawer-overlay").hidden = true;
  if (lastFocused && lastFocused.focus) lastFocused.focus();
}

/* ---------------------------- process modal ---------------------------- */

function openModal() {
  if (state.lastBatch) $("#batch-input").value = JSON.stringify(state.lastBatch, null, 2);
  $("#modal-status").textContent = "";
  $("#modal-status").className = "modal-status";
  $("#modal-overlay").hidden = false;
  $("#process-modal").hidden = false;
  $("#batch-input").focus();
}
function closeModal() {
  $("#process-modal").hidden = true;
  $("#modal-overlay").hidden = true;
}
async function runFromModal() {
  let batch;
  try {
    batch = JSON.parse($("#batch-input").value || "[]");
  } catch (err) {
    $("#modal-status").textContent = "Invalid JSON: " + err.message;
    $("#modal-status").className = "modal-status error";
    return;
  }
  if (!Array.isArray(batch)) {
    $("#modal-status").textContent = "Batch must be a JSON array of source items.";
    $("#modal-status").className = "modal-status error";
    return;
  }
  const ok = await processBatch(batch);
  if (ok) closeModal();
}
async function insertSampleIntoModal() {
  try {
    const res = await fetch("/api/sample");
    const data = await res.json();
    $("#batch-input").value = JSON.stringify(data.batch, null, 2);
    $("#modal-status").textContent = "Sample batch inserted — press Run batch.";
    $("#modal-status").className = "modal-status ok";
  } catch (err) {
    $("#modal-status").textContent = "Could not fetch sample: " + err.message;
    $("#modal-status").className = "modal-status error";
  }
}

/* ---------------------------- export + raw ----------------------------- */

function exportJson() {
  if (!state.data) { toast("Nothing to export yet — load or process a batch", "error"); return; }
  const blob = new Blob([JSON.stringify(state.data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "transformbiz-deals.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast("Exported results to JSON", "ok");
}

function toggleRaw() {
  const panel = $("#raw-panel");
  const btn = $("#toggle-raw");
  const show = panel.hidden;
  panel.hidden = !show;
  btn.setAttribute("aria-pressed", String(show));
}

/* ---------------------------- tabs ------------------------------------- */

function switchTab(name) {
  state.tab = name;
  $$(".tab").forEach((t) => {
    const active = t.dataset.tab === name;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", String(active));
  });
  $$(".view").forEach((v) => { v.hidden = v.id !== "view-" + name; });
}

/* ---------------------------- wiring ----------------------------------- */

function bindEvents() {
  $("#refresh-now").addEventListener("click", refreshNow);
  $("#load-sample").addEventListener("click", loadSample);
  $("#open-process").addEventListener("click", openModal);
  $("#export-json").addEventListener("click", exportJson);
  $("#toggle-raw").addEventListener("click", toggleRaw);

  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-run").addEventListener("click", runFromModal);
  $("#modal-fill-sample").addEventListener("click", insertSampleIntoModal);
  $("#modal-overlay").addEventListener("click", closeModal);

  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#drawer-overlay").addEventListener("click", closeDrawer);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!$("#process-modal").hidden) closeModal();
      else if (!$("#drawer").hidden) closeDrawer();
    }
  });

  $$(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));

  // Filters
  $("#search").addEventListener("input", (e) => { state.filters.search = e.target.value; renderDeals(); });
  $("#f-class").addEventListener("change", (e) => { state.filters.classification = e.target.value; renderDeals(); });
  $("#f-source").addEventListener("change", (e) => { state.filters.source = e.target.value; renderDeals(); });
  $("#f-sector").addEventListener("change", (e) => { state.filters.sector = e.target.value; renderDeals(); });
  $("#f-franchise").addEventListener("change", (e) => { state.filters.franchiseOnly = e.target.checked; renderDeals(); });
  $("#f-hide-stale").addEventListener("change", (e) => { state.filters.hideStale = e.target.checked; renderDeals(); });
  $("#f-score").addEventListener("input", (e) => {
    state.filters.minScore = Number(e.target.value);
    $("#score-out").textContent = e.target.value;
    renderDeals();
  });
}

bindEvents();
// On first paint, load the latest synced snapshot from the DB so the dashboard
// reflects persisted state. Then keep the per-source status badges fresh.
refreshNow();
pollStatus();
setInterval(pollStatus, 30000);
