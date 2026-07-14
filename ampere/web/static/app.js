// Ampere SPA (M4). Renders the five screens from the FastAPI backend (/api/*).
// Scoring / dedup / Pareto frontier are computed SERVER-SIDE in the Python domain layer and are
// never re-implemented here. This file only: fetches, maps domain numbers to SVG pixels, and does
// pure-view client-side filtering + sorting. Moving a weight slider re-fetches (the server
// re-scores) — that is the "sliders re-score live" path. Design of record: design/Ampere.dc.html.

const TITLES = {
  dashboard: ["Pareto frontier", "— capability vs effective price"],
  listings: ["Listings", "— deduped SKUs"],
  catalog: ["Catalog", "— reference DB"],
  changes: ["Watchlist", "— price drops / new arrivals"],
  settings: ["Settings", ""],
};

const state = {
  screen: "dashboard",
  w_perf: 0.55,
  blended: false,
  mall_only: false,
  frontier_only: false,
  brand: "all",
  cond: "all",
  conf: "all",
  sortKey: "value",
  sortDir: "desc",
  cache: {},
};

// --- helpers ---------------------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const fmt = (n) => "Rp " + Math.round(n).toLocaleString("id-ID");
const jt = (n) => (n / 1e6).toFixed(2) + "jt";
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, params) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const r = await fetch("/api" + path + qs);
  if (!r.ok) throw new Error(path + " -> " + r.status);
  return r.json();
}
async function apiPost(path, body) {
  const r = await fetch("/api" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : null,
  });
  if (!r.ok) throw new Error(path + " -> " + r.status);
  return r.json();
}

const serverParams = () => ({ w_perf: state.w_perf, blended: state.blended });

// --- load + chrome ---------------------------------------------------------------------------
async function load(screen) {
  state.screen = screen;
  for (const b of document.querySelectorAll(".nav-item"))
    b.classList.toggle("active", b.dataset.screen === screen);
  const content = $("#content");
  content.innerHTML = `<div class="loading">loading ${esc(screen)}…</div>`;
  try {
    const data = await api("/" + screen, screen === "catalog" ? undefined : serverParams());
    state.cache[screen] = data;
    renderChrome(data.meta);
    RENDER[screen](data);
  } catch (e) {
    content.innerHTML = `<div class="scaffold-note">Failed to load <code>${esc(screen)}</code>: ${esc(e.message)}</div>`;
  }
}

function renderChrome(meta) {
  if (!meta) return;
  $("#chip-keyword").textContent = meta.keyword;
  $("#chip-band").textContent = "band: " + meta.band_label;
  $("#stat-raw").textContent = meta.stats.raw;
  $("#stat-deduped").textContent = meta.stats.deduped;
  $("#stat-matched").textContent = meta.stats.matched_pct;
  $("#stat-schedule").textContent = "daily " + meta.schedule.time;
  $("#foot-snapshot").textContent = meta.snapshot_date || "—";
  $("#foot-version").textContent = meta.scoring_version;
  const b = meta.nav_badges;
  const set = (name, v) => { const n = document.querySelector(`[data-badge="${name}"]`); if (n) n.textContent = v || ""; };
  set("listings", b.listings);
  set("catalog", b.catalog);
  set("changes", b.changes);
}

// --- dashboard -------------------------------------------------------------------------------
function renderDashboard(data) {
  let pts = data.points.slice();
  if (state.mall_only) pts = pts.filter((p) => p.is_mall);
  if (state.frontier_only) pts = pts.filter((p) => p.is_frontier);

  $("#content").innerHTML = `
    <div class="screen-head">
      <h1>Pareto frontier <span class="dim">— capability vs effective price</span></h1>
      <div class="toolbar">
        <label><input type="checkbox" id="cb-frontier" ${state.frontier_only ? "checked" : ""}> frontier only</label>
        <label><input type="checkbox" id="cb-blended" ${state.blended ? "checked" : ""}> blend conditions</label>
        <label><input type="checkbox" id="cb-mall" ${state.mall_only ? "checked" : ""}> Mall only</label>
      </div>
    </div>
    <div class="dash-grid">
      <div class="chart-panel">
        ${scatterSvg(pts, data.meta)}
        <div class="legend">
          <span><span class="dot dot-frontier"></span>frontier</span>
          <span><span class="dot dot-dominated"></span>dominated</span>
          <span><span class="dot dot-used"></span>used / second</span>
        </div>
        <div id="tooltip" class="tooltip" hidden></div>
      </div>
      <div class="side-col">
        <div class="panel">
          <div class="panel-head"><span>TOP OF FRONTIER — VALUE RANKED</span><span class="accent">cap / juta</span></div>
          ${data.top_frontier.map(frontierRow).join("") || `<div class="panel-row dim">no frontier points</div>`}
        </div>
        ${weightsPanel(data.weights)}
      </div>
    </div>`;

  $("#cb-frontier").onchange = (e) => { state.frontier_only = e.target.checked; renderDashboard(state.cache.dashboard); };
  $("#cb-mall").onchange = (e) => { state.mall_only = e.target.checked; renderDashboard(state.cache.dashboard); };
  $("#cb-blended").onchange = (e) => { state.blended = e.target.checked; load("dashboard"); };
  wireWeightSlider("dashboard");
  wireScatterHover(pts, data.meta);
}

function scatterSvg(pts, meta) {
  const padL = 56, padT = 20, plotW = 680, plotH = 366;
  const x0 = meta.price_min, x1 = meta.price_max || x0 + 1;
  const px = (v) => padL + ((v - x0) / (x1 - x0)) * plotW;
  const py = (v) => padT + (1 - v / 100) * plotH;

  const yTicks = [0, 20, 40, 60, 80, 100]
    .map((v) => `<line x1="56" y1="${py(v).toFixed(1)}" x2="736" y2="${py(v).toFixed(1)}" class="grid-y"></line>
      <text x="48" y="${(py(v) + 3).toFixed(1)}" text-anchor="end" class="tick">${v}</text>`).join("");
  const xVals = [x0, x0 + (x1 - x0) * 0.25, x0 + (x1 - x0) * 0.5, x0 + (x1 - x0) * 0.75, x1];
  const xTicks = xVals
    .map((v) => `<line x1="${px(v).toFixed(1)}" y1="20" x2="${px(v).toFixed(1)}" y2="386" class="grid-x"></line>
      <text x="${px(v).toFixed(1)}" y="402" text-anchor="middle" class="tick">${jt(v)}</text>`).join("");

  // frontier polylines, one per condition group (or one when blended)
  const frontier = pts.filter((p) => p.is_frontier);
  const groups = state.blended ? { all: frontier } : groupBy(frontier, (p) => p.condition);
  const lines = Object.entries(groups)
    .map(([cond, arr]) => {
      const sorted = arr.slice().sort((a, b) => a.effective_price - b.effective_price);
      if (sorted.length < 2) return "";
      const d = sorted.map((p) => `${px(p.effective_price).toFixed(1)},${py(p.capability).toFixed(1)}`).join(" ");
      const used = cond === "used";
      return `<polyline points="${d}" fill="none" stroke="#c6ff3a" stroke-width="1.5" stroke-dasharray="${used ? "4 3" : "0"}" opacity="${used ? 0.5 : 0.9}"></polyline>`;
    }).join("");

  const circles = pts
    .map((p, i) => {
      const used = p.condition === "used";
      return `<circle data-i="${i}" cx="${px(p.effective_price).toFixed(1)}" cy="${py(p.capability).toFixed(1)}"
        r="${p.is_frontier ? 5.5 : 4}" fill="${p.is_frontier ? "#c6ff3a" : "#20261c"}"
        stroke="${p.is_frontier ? "#c6ff3a" : used ? "#8a9081" : "#3a4033"}"
        stroke-width="${used ? 1.4 : 1}" stroke-dasharray="${used ? "2 2" : "0"}"
        opacity="${p.is_frontier ? 1 : 0.72}" class="pt"></circle>`;
    }).join("");

  return `<svg width="760" height="430" viewBox="0 0 760 430" id="scatter">
    ${yTicks}${xTicks}
    <text x="396" y="424" text-anchor="middle" class="axis-label">EFFECTIVE PRICE (IDR)</text>
    <text x="16" y="203" text-anchor="middle" class="axis-label" transform="rotate(-90 16 203)">CAPABILITY</text>
    ${lines}${circles}
  </svg>`;
}

function wireScatterHover(pts, meta) {
  const tip = $("#tooltip");
  const svg = $("#scatter");
  if (!svg || !tip) return;
  const padL = 56, padT = 20, plotW = 680, plotH = 366;
  const x0 = meta.price_min, x1 = meta.price_max || x0 + 1;
  const px = (v) => padL + ((v - x0) / (x1 - x0)) * plotW;
  const py = (v) => padT + (1 - v / 100) * plotH;
  for (const c of svg.querySelectorAll("circle.pt")) {
    c.addEventListener("mouseenter", () => {
      const p = pts[+c.dataset.i];
      tip.innerHTML = `
        <div class="tt-model">${esc(p.model)}</div>
        <div class="tt-sub">${esc(p.variant)} · ${esc(p.chip)} · ${esc(p.condition)}${p.is_mall ? " · Mall" : ""}</div>
        <div class="tt-row"><span>capability</span><span class="accent">${p.capability.toFixed(1)}</span></div>
        <div class="tt-row"><span>eff. price</span><span>${fmt(p.effective_price)}</span></div>
        <div class="tt-row"><span>value</span><span>${p.value.toFixed(1)}</span></div>
        <div class="tt-row"><span>verdict</span><span style="color:${p.is_frontier ? "#c6ff3a" : "#ff6b6b"}">${esc(p.verdict)}</span></div>`;
      tip.style.left = (px(p.effective_price) * (760 / 760)) + "px";
      tip.style.top = py(p.capability) + "px";
      tip.hidden = false;
    });
    c.addEventListener("mouseleave", () => { tip.hidden = true; });
  }
}

const frontierRow = (r) => `
  <div class="panel-row frontier-row">
    <span class="rank">${String(r.rank).padStart(2, "0")}</span>
    <div class="fr-model">
      <div class="name">${esc(r.model)} <span class="dim">${esc(r.variant)}</span></div>
      <div class="sub">${esc(r.chip)} · ${fmt(r.effective_price)}</div>
    </div>
    <div class="fr-val"><div class="val accent">${r.value.toFixed(1)}</div><div class="sub">cap ${r.capability.toFixed(1)}</div></div>
  </div>`;

function weightsPanel(weights) {
  return `<div class="panel weights-panel">
    <div class="set-label">CAPABILITY WEIGHTING</div>
    <div class="w-row"><span class="dim">performance</span><span class="accent" id="w-perf-val">${weights.w_perf.toFixed(2)}</span></div>
    <input type="range" min="0" max="1" step="0.05" value="${weights.w_perf}" id="w-perf" />
    <div class="w-row"><span class="dim">battery endurance</span><span id="w-batt-val">${weights.w_batt.toFixed(2)}</span></div>
    <div class="w-note">perf blend = GB6·2 / AnTuTu / Wild Life Extreme, evenly weighted. Battery is a co-equal pillar, not a tiebreaker.</div>
  </div>`;
}

let _weightTimer = null;
function wireWeightSlider(screen) {
  const slider = $("#w-perf");
  if (!slider) return;
  slider.addEventListener("input", (e) => {
    state.w_perf = parseFloat(e.target.value);
    const pv = $("#w-perf-val"), bv = $("#w-batt-val");
    if (pv) pv.textContent = state.w_perf.toFixed(2);
    if (bv) bv.textContent = (1 - state.w_perf).toFixed(2);
    clearTimeout(_weightTimer);
    _weightTimer = setTimeout(() => load(screen), 140); // debounce -> server re-scores
  });
}

// --- listings --------------------------------------------------------------------------------
function renderListings(data) {
  const brands = ["all", ...Array.from(new Set(data.rows.map((r) => r.brand))).sort()];
  const rows = filterSortListings(data.rows);
  const chip = (active, label, on) =>
    `<button class="chip-btn ${active ? "active" : ""}" data-act="${on}">${esc(label)}</button>`;

  $("#content").innerHTML = `
    <div class="screen-head"><h1>Listings <span class="dim">— ${rows.length} of ${data.rows.length} deduped SKUs</span></h1></div>
    <div class="filter-bar">
      ${brands.map((b) => chip(state.brand === b, b === "all" ? "ALL" : b, "brand:" + b)).join("")}
      <span class="sep"></span>
      ${[["all", "ANY"], ["new", "NEW"], ["used", "USED"]].map(([k, l]) => chip(state.cond === k, l, "cond:" + k)).join("")}
      <span class="sep"></span>
      ${[["all", "ALL"], ["full", "FULL"], ["partial", "PARTIAL"]].map(([k, l]) => chip(state.conf === k, l, "conf:" + k)).join("")}
      <span class="sep"></span>
      ${chip(state.frontier_only, "FRONTIER ONLY", "frontier_only")}
      ${chip(state.mall_only, "MALL ONLY", "mall_only")}
    </div>
    <div class="panel table listings-table">
      <div class="table-head lst-grid">
        ${col("model", "MODEL / LISTING")}${col("chip", "CHIPSET")}${col("effective_price", "EFF. PRICE")}
        ${col("capability", "CAP")}${col("value", "VALUE")}<span>CONF</span><span>SELLER</span><span></span>
      </div>
      ${rows.map(listingRow).join("") || `<div class="table-row dim">no listings match</div>`}
    </div>`;

  for (const b of document.querySelectorAll(".filter-bar .chip-btn")) {
    b.onclick = () => {
      const [k, v] = b.dataset.act.split(":");
      if (k === "brand") state.brand = v;
      else if (k === "cond") state.cond = v;
      else if (k === "conf") state.conf = v;
      else if (k === "frontier_only") state.frontier_only = !state.frontier_only;
      else if (k === "mall_only") state.mall_only = !state.mall_only;
      renderListings(state.cache.listings);
    };
  }
  for (const h of document.querySelectorAll(".table-head [data-sort]")) {
    h.onclick = () => {
      const key = h.dataset.sort;
      if (state.sortKey === key) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      else { state.sortKey = key; state.sortDir = "desc"; }
      renderListings(state.cache.listings);
    };
  }
}

function col(key, label) {
  const arrow = state.sortKey === key ? (state.sortDir === "asc" ? " ▲" : " ▼") : "";
  return `<button class="sort-col ${state.sortKey === key ? "on" : ""}" data-sort="${key}">${esc(label)}<span class="accent">${arrow}</span></button>`;
}

function filterSortListings(rows) {
  const s = state;
  let out = rows.filter(
    (r) =>
      (s.brand === "all" || r.brand === s.brand) &&
      (s.cond === "all" || r.condition === s.cond) &&
      (s.conf === "all" || r.confidence === s.conf) &&
      (!s.mall_only || r.is_mall) &&
      (!s.frontier_only || r.is_frontier)
  );
  const dir = s.sortDir === "asc" ? 1 : -1;
  out.sort((a, b) => {
    const av = a[s.sortKey], bv = b[s.sortKey];
    if (typeof av === "string") return dir * String(av).localeCompare(String(bv));
    return dir * ((av || 0) - (bv || 0));
  });
  return out;
}

const listingRow = (r) => `
  <div class="table-row lst-grid">
    <div class="cell-model">
      <div class="line">
        <span class="name">${esc(r.model)} <span class="dim">${esc(r.variant)}</span></span>
        ${r.is_frontier ? `<span class="tag tag-frontier">FRONTIER</span>` : ""}
        ${r.duplicate_count > 1 ? `<span class="dim">×${r.duplicate_count}</span>` : ""}
      </div>
      <div class="sub ellipsis">${esc(r.title)}</div>
    </div>
    <div class="dim">${esc(r.chip)}</div>
    <div>${fmt(r.effective_price)}${r.price_drop ? `<div class="drop">▼ ${jt(r.price_drop)}</div>` : ""}</div>
    <div class="accent">${r.capability.toFixed(1)}</div>
    <div>${r.value.toFixed(1)}</div>
    <div><span class="tag ${r.confidence === "full" ? "tag-full" : "tag-partial"}">${esc(r.confidence)}</span></div>
    <div class="cell-seller">
      <div class="line">
        <span>★${r.seller_rating != null ? r.seller_rating.toFixed(1) : "—"}</span>
        ${r.is_mall ? `<span class="tag tag-frontier">MALL</span>` : ""}
        ${r.is_star_seller ? `<span class="tag tag-star">STAR+</span>` : ""}
      </div>
      <div class="sub">${esc(r.seller_location || "")}</div>
    </div>
    <div class="right">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">open →</a>` : `<span class="dim">—</span>`}</div>
  </div>`;

// --- catalog ---------------------------------------------------------------------------------
function renderCatalog(data) {
  $("#content").innerHTML = `
    <div class="screen-head"><h1>Catalog <span class="dim">— reference DB</span></h1></div>
    <div class="catalog-grid">
      <div class="cat-main">
        <div class="set-label">CHIPSET BENCHMARKS <span class="dim">· one row per SoC · refreshed monthly · GSMArena</span></div>
        <div class="panel table">
          <div class="table-head chip-grid dim">
            <span>CHIPSET</span><span class="right">GB6 S</span><span class="right">GB6 M</span>
            <span class="right">AnTuTu v10</span><span class="right">WLE Hi</span><span class="right">used by</span>
          </div>
          ${data.chipsets.map(chipRow).join("")}
        </div>
        <div class="set-label mt">DEVICE ROWS <span class="dim">· battery + update longevity are per-device</span></div>
        <div class="panel table">
          <div class="table-head dev-grid dim">
            <span>DEVICE</span><span>CHIPSET</span><span class="right">ACTIVE USE</span>
            <span class="right">OS / SEC yr</span><span class="right">SOURCE</span>
          </div>
          ${data.devices.map(deviceRow).join("")}
        </div>
      </div>
      <div class="cat-side">
        <div class="set-label warn">NEEDS MAPPING QUEUE <span class="dim">· ${data.needs_mapping.length} unresolved</span></div>
        <div class="panel needs-queue">
          ${data.needs_mapping.map(needsItem).join("") || `<div class="panel-row dim">queue empty</div>`}
          <div class="needs-note">Mapped aliases are remembered so the gap is closed once — the next run resolves the listing.</div>
        </div>
      </div>
    </div>`;

  for (const btn of document.querySelectorAll(".needs-item .map-btn")) {
    btn.onclick = async () => {
      const item = btn.closest(".needs-item");
      const device_id = item.querySelector("input").value.trim();
      const title = item.dataset.title;
      if (!device_id) return;
      btn.disabled = true; btn.textContent = "…";
      try {
        await apiPost("/catalog/map", { title, device_id });
        item.innerHTML = `<div class="mapped">✓ mapped → <span class="accent">${esc(device_id)}</span> · runs next fetch</div>`;
      } catch (e) {
        btn.disabled = false; btn.textContent = "map";
        alert("map failed: " + e.message);
      }
    };
  }
}

const numOrDash = (n) => (n == null ? "—" : Math.round(n).toLocaleString("en-US"));
const chipRow = (c) => `
  <div class="table-row chip-grid">
    <span>${esc(c.name)}</span>
    <span class="right">${numOrDash(c.gb6_single)}</span>
    <span class="right">${numOrDash(c.gb6_multi)}</span>
    <span class="right">${numOrDash(c.antutu)}</span>
    <span class="right">${numOrDash(c.wildlife)}</span>
    <span class="right accent">${c.used_by}</span>
  </div>`;
const deviceRow = (d) => `
  <div class="table-row dev-grid">
    <span>${esc(d.brand)} ${esc(d.model)} <span class="dim">${esc(d.variant)}</span></span>
    <span class="dim">${esc(d.chip)}</span>
    <span class="right">${d.active_use_hours != null ? d.active_use_hours.toFixed(1) + "h" : "—"}
      <span class="tag ${d.battery_metric_kind === "endurance" ? "tag-legacy" : "tag-mut"}">${d.battery_metric_kind === "endurance" ? "LEGACY" : "v2"}</span></span>
    <span class="right">${d.os_updates_years ?? "—"} / ${d.security_updates_years ?? "—"}</span>
    <span class="right sub">${esc(d.update_source || "—")}</span>
  </div>`;
const needsItem = (n) => `
  <div class="needs-item" data-title="${esc(n.title)}">
    <div class="nq-title">${esc(n.title)}</div>
    <div class="nq-actions">
      <input placeholder="device_id (e.g. dev-rn13-8-256)…" />
      <button class="btn map-btn">map</button>
    </div>
  </div>`;

// --- changes ---------------------------------------------------------------------------------
function renderChanges(data) {
  $("#content").innerHTML = `
    <div class="screen-head"><h1>Watchlist <span class="dim">— vs snapshot ${esc(data.prior_date || "—")}</span></h1></div>
    <div class="changes-grid">
      <div>
        <div class="set-label accent">PRICE DROPS <span class="dim">· ${data.price_drops.length} today</span></div>
        <div class="panel">
          ${data.price_drops.map(dropRow).join("") || `<div class="panel-row dim">no price drops</div>`}
        </div>
      </div>
      <div>
        <div class="set-label">NEW ARRIVALS <span class="dim">· ${data.new_arrivals.length} today</span></div>
        <div class="panel">
          ${data.new_arrivals.map(arrivalRow).join("") || `<div class="panel-row dim">no new arrivals</div>`}
        </div>
      </div>
    </div>`;
}
const dropRow = (r) => `
  <div class="panel-row change-row">
    <div class="cr-model"><div class="name">${esc(r.model || "—")} <span class="dim">${esc(r.variant || "")}</span></div>
      <div class="sub">${esc(r.chip)} · cap ${r.capability != null ? r.capability.toFixed(1) : "—"}</div></div>
    <div class="right"><div>${fmt(r.effective_price)}</div><div class="sub strike">${fmt(r.prior_effective_price)}</div></div>
    <div class="cr-delta accent">▼ ${jt(-r.delta)}</div>
  </div>`;
const arrivalRow = (r) => `
  <div class="panel-row change-row">
    <span class="new-dot"></span>
    <div class="cr-model"><div class="name">${esc(r.model || "—")} <span class="dim">${esc(r.variant || "")}</span></div>
      <div class="sub">${esc(r.chip)} · ${fmt(r.effective_price)}</div></div>
    ${r.is_frontier ? `<span class="tag tag-frontier">ON FRONTIER</span>` : ""}
    <div class="cr-delta accent">${r.value != null ? r.value.toFixed(1) : "—"}</div>
  </div>`;

// --- settings --------------------------------------------------------------------------------
function renderSettings(data) {
  const toggle = (on, label, note) =>
    `<label class="set-toggle"><span>${esc(label)} <span class="dim">${esc(note)}</span></span><input type="checkbox" ${on ? "checked" : ""} disabled></label>`;
  $("#content").innerHTML = `
    <div class="screen-head"><h1>Settings</h1></div>
    <div class="settings">
      <div class="set-section">
        <div class="set-label">QUERY</div>
        <div class="set-fields">
          <label>keyword<input value="${esc(data.keyword)}" readonly></label>
          <label>price min (IDR)<input value="${data.price_min}" readonly></label>
          <label>price max (IDR)<input value="${data.price_max}" readonly></label>
        </div>
      </div>
      <div class="set-section">
        <div class="set-label">SCORING WEIGHTS <span class="dim">· scoring_version ${esc(data.scoring_version)}</span></div>
        <div class="w-row"><span class="dim">W_PERF performance</span><span class="accent" id="w-perf-val">${data.weights.w_perf.toFixed(2)}</span></div>
        <input type="range" min="0" max="1" step="0.05" value="${data.weights.w_perf}" id="w-perf" />
        <div class="perf-chips">
          ${Object.entries(data.perf_weights).map(([k, v]) => `<span class="perf-chip">${esc(k)} ·${(v * 100).toFixed(0)}</span>`).join("")}
          <span class="perf-chip w-batt-chip">W_BATT battery ·<span id="w-batt-val">${data.weights.w_batt.toFixed(2)}</span></span>
        </div>
      </div>
      <div class="set-section">
        <div class="set-label">FILTERS &amp; TOGGLES</div>
        ${toggle(data.mall_only, "Mall only", '(SHOP_TYPE=OFFICIAL_MALL — practical "new" proxy)')}
        ${toggle(data.blended, "Blend conditions in frontier", "(off = new vs new, used vs used)")}
        ${toggle(data.longevity_bonus_enabled, "Longevity bonus", "(fold OS-update years into capability)")}
        ${toggle(data.trust_penalty_enabled, "Trust penalty on value", "(soft-penalize low-trust listings)")}
      </div>
      <div class="set-section">
        <div class="set-label">SOURCE</div>
        <div class="filter-bar">
          ${data.sources.map((s) => `<span class="chip-btn ${s === data.source_kind ? "active" : ""}">${esc(s)}</span>`).join("")}
        </div>
        <div class="set-run">
          <div class="dim run-note">Runs unattended once per day (idempotent + transactional per snapshot_date). This button is a fallback only.</div>
          <button class="btn btn-primary" id="run-now">Run now</button>
        </div>
        <div class="schedule-box">
          <span class="schedule-dot"></span>
          <div><div class="accent">SCHEDULE ACTIVE</div><div class="dim">daily ${esc(data.schedule.time)} · last run ${esc(data.schedule.last_run || "—")}</div></div>
        </div>
      </div>
    </div>`;

  wireWeightSlider("settings");
  $("#run-now").onclick = async (e) => {
    const btn = e.target; btn.disabled = true; btn.textContent = "running…";
    try {
      const res = await apiPost("/run");
      btn.textContent = `✓ ${res.listing_count} listings · ${res.frontier_size} on frontier`;
      setTimeout(() => load("settings"), 900);
    } catch (err) {
      btn.disabled = false; btn.textContent = "Run now";
      alert("run failed: " + err.message);
    }
  };
}

// --- util + boot -----------------------------------------------------------------------------
function groupBy(arr, keyfn) {
  const m = {};
  for (const x of arr) (m[keyfn(x)] = m[keyfn(x)] || []).push(x);
  return m;
}

const RENDER = {
  dashboard: renderDashboard,
  listings: renderListings,
  catalog: renderCatalog,
  changes: renderChanges,
  settings: renderSettings,
};

const currentScreen = () => {
  const s = location.hash.slice(1);
  return RENDER[s] ? s : "dashboard";
};

document.getElementById("nav").addEventListener("click", (e) => {
  const btn = e.target.closest(".nav-item");
  if (!btn) return;
  if (location.hash.slice(1) === btn.dataset.screen) load(btn.dataset.screen);
  else location.hash = btn.dataset.screen; // hashchange -> load (deep-linkable + refresh-safe)
});
window.addEventListener("hashchange", () => load(currentScreen()));

load(currentScreen());
