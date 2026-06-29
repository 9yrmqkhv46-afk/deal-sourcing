"use strict";

const state = {
  data: null,
  sort: { key: "overall_score", dir: "desc" },
  filter: "all",
};

const $ = (sel) => document.querySelector(sel);

function setStatus(msg, kind) {
  const el = $("#status");
  el.textContent = msg || "";
  el.className = "status" + (kind ? " " + kind : "");
}

async function loadSample() {
  setStatus("Loading sample batch...");
  try {
    const res = await fetch("/api/sample");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    $("#batch-input").value = JSON.stringify(data.batch, null, 2);
    await processBatch(data.batch);
  } catch (err) {
    setStatus("Failed to load sample: " + err.message, "error");
  }
}

async function runFromTextarea() {
  let batch;
  try {
    batch = JSON.parse($("#batch-input").value || "[]");
  } catch (err) {
    setStatus("Invalid JSON: " + err.message, "error");
    return;
  }
  await processBatch(batch);
}

async function processBatch(batch) {
  setStatus("Processing " + batch.length + " item(s)...");
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
    render();
    setStatus("Processed successfully.", "ok");
  } catch (err) {
    setStatus("Processing failed: " + err.message, "error");
  }
}

function classBadge(cls) {
  const map = {
    core_thesis: ["badge-core", "Core"],
    adjacent_thesis: ["badge-adjacent", "Adjacent"],
    reject: ["badge-reject", "Reject"],
  };
  const [klass, label] = map[cls] || ["badge-reject", cls];
  return `<span class="badge ${klass}">${label}</span>`;
}

function companyName(companyId) {
  const c = (state.data.companies || []).find((x) => x.company_id === companyId);
  return c ? c.name : "—";
}

function render() {
  if (!state.data) return;
  const s = state.data.summary;
  $("#count-core").textContent = s.core_thesis_deal_count;
  $("#count-adjacent").textContent = s.adjacent_thesis_deal_count;
  $("#count-reject").textContent = s.reject_count;
  $("#count-total").textContent = state.data.deals.length;

  $("#summary-cards").hidden = false;
  $("#deals-section").hidden = false;
  $("#companies-section").hidden = false;
  $("#founders-section").hidden = false;
  $("#contacts-section").hidden = false;

  renderFilterChips();
  renderDeals();
  renderCompanies();
  renderFounders();
  renderContacts();
}

function renderFilterChips() {
  const chips = [
    ["all", "All"],
    ["core_thesis", "Core"],
    ["adjacent_thesis", "Adjacent"],
    ["reject", "Reject"],
  ];
  $("#filter-chips").innerHTML = chips
    .map(
      ([k, label]) =>
        `<span class="chip ${state.filter === k ? "active" : ""}" data-filter="${k}">${label}</span>`
    )
    .join("");
  document.querySelectorAll("#filter-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.filter = chip.dataset.filter;
      render();
    });
  });
}

function sortedDeals() {
  let deals = state.data.deals.slice();
  if (state.filter !== "all") {
    deals = deals.filter((d) => d.thesis_match.classification === state.filter);
  }
  const { key, dir } = state.sort;
  const val = (d) => {
    switch (key) {
      case "overall_score": return d.thesis_match.overall_score;
      case "classification": return d.thesis_match.classification;
      case "company": return companyName(d.company_id);
      case "source_type": return d.source_type;
      case "deal_size_bucket": return d.deal_size_bucket;
      default: return (d.title || "").toLowerCase();
    }
  };
  deals.sort((a, b) => {
    const av = val(a), bv = val(b);
    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return a.deal_id < b.deal_id ? -1 : 1;
  });
  return deals;
}

function renderDeals() {
  const body = $("#deals-body");
  body.innerHTML = sortedDeals()
    .map((d) => {
      const tm = d.thesis_match;
      return `<tr>
        <td>${escapeHtml(d.title)}<div class="explanation">${escapeHtml(tm.explanation)}</div></td>
        <td>${escapeHtml(companyName(d.company_id))}</td>
        <td>${escapeHtml(d.source_type)}</td>
        <td>${escapeHtml(d.deal_size_bucket)}</td>
        <td><span class="score-pill">${tm.overall_score}</span></td>
        <td>${classBadge(tm.classification)}</td>
      </tr>`;
    })
    .join("");

  document.querySelectorAll("#deals-table th[data-sort]").forEach((th) => {
    th.onclick = () => {
      const key = th.dataset.sort;
      if (state.sort.key === key) {
        state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
      } else {
        state.sort.key = key;
        state.sort.dir = key === "overall_score" ? "desc" : "asc";
      }
      render();
    };
    th.classList.toggle("active", th.dataset.sort === state.sort.key);
  });
}

function renderCompanies() {
  $("#companies-list").innerHTML = (state.data.companies || [])
    .map((c) => {
      const banned = c.banned_sector_flag ? ' <span class="badge badge-reject">excluded sector</span>' : "";
      const bits = [c.sector, c.state, c.country, c.age_years != null ? c.age_years + "y" : null]
        .filter(Boolean)
        .join(" · ");
      return `<li><div class="entity-name">${escapeHtml(c.name)}${banned}</div>
        <div class="entity-meta">${escapeHtml(bits || "details unknown")}</div></li>`;
    })
    .join("");
}

function renderFounders() {
  const founders = state.data.founders || [];
  $("#founders-section").hidden = founders.length === 0;
  $("#founders-list").innerHTML = founders
    .map((f) => {
      const bits = [f.role, f.tenure_years != null ? f.tenure_years + "y tenure" : null, f.organization_name]
        .filter(Boolean)
        .join(" · ");
      return `<li><div class="entity-name">${escapeHtml(f.name)}</div>
        <div class="entity-meta">${escapeHtml(bits)}</div></li>`;
    })
    .join("");
}

function renderContacts() {
  const contacts = state.data.summary.top_contacts_for_outreach || [];
  $("#contacts-section").hidden = contacts.length === 0;
  $("#contacts-list").innerHTML = contacts
    .map((c) => {
      const meta = [c.role_or_title, c.sector_focus, c.region_or_state].filter(Boolean).join(" · ");
      const reach = [c.email, c.phone].filter(Boolean).join(" · ");
      return `<li>
        <div class="entity-name">${escapeHtml(c.person_or_org_name)}</div>
        <div class="entity-meta">${escapeHtml(meta)}${reach ? " — " + escapeHtml(reach) : ""}</div>
        <div class="priority-reason">${escapeHtml(c.priority_reason || "")}</div>
      </li>`;
    })
    .join("");
}

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

$("#load-sample").addEventListener("click", loadSample);
$("#run-batch").addEventListener("click", runFromTextarea);
