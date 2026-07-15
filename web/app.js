"use strict";

// DEMO mode: when served as the static showcase (web/demo/), window.JOBHUNT_DEMO
// is set and all data comes from a baked-in snapshot instead of the Python API.
// Inert in the real app (flag unset).
const DEMO = !!(typeof window !== "undefined" && window.JOBHUNT_DEMO);
const DEMO_DATA = (typeof window !== "undefined" && window.JOBHUNT_DEMO_DATA) || null;

// --------------------------------------------------------------------------- //
// tiny API layer
// --------------------------------------------------------------------------- //
const api = {
  async get(path) {
    if (DEMO) return demoGet(path);
    const r = await fetch(path);
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  },
  async post(path, body) {
    if (DEMO) return demoPost(path, body || {});
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  },
};

const $ = (sel) => document.querySelector(sel);
const state = { transit: {}, home: null, statuses: [], markers: new Map(), active: null, map: null, view: "new",
                jobsData: null, radius: { on: false, miles: 3, circle: null } };

// After this many days with an application and no status change, the card
// offers a one-click follow-up email.
const FOLLOWUP_DAYS = 5;

// Triage tabs: which status each view shows.
const VIEWS = [
  { key: "latest", label: "🆕 Just fetched" },
  { key: "new", label: "To review" },
  { key: "interested", label: "★ Interested" },
  { key: "applied", label: "Applied" },
  { key: "rejected", label: "✕ Not interested" },
  { key: "all", label: "All" },
];

function toast(msg, ms = 2400) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), ms);
}

// --------------------------------------------------------------------------- //
// map
// --------------------------------------------------------------------------- //
function scoreColor(s) {
  if (s >= 18) return "#059669";   // strong fit
  if (s >= 10) return "#2563eb";   // good
  if (s >= 4)  return "#64748b";   // ok
  return "#94a3b8";                // weak
}

function initMap(home, transit) {
  const map = L.map("map", { zoomControl: true }).setView([home.lat, home.lng], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  // transit lines: subway solid + thick, buses dashed + thin
  for (const line of Object.values(transit)) {
    const latlngs = line.stops.map((s) => [s[1], s[2]]);
    const isBus = line.kind === "bus";
    L.polyline(latlngs, {
      color: line.color,
      weight: isBus ? 2.5 : 5,
      opacity: isBus ? 0.7 : 0.9,
      dashArray: isBus ? "4 6" : null,
    }).addTo(map).bindTooltip(line.name, { sticky: true });

    if (!isBus) {
      for (const [name, lat, lng] of line.stops) {
        L.circleMarker([lat, lng], {
          radius: 3, color: "#fff", weight: 1.5, fillColor: line.color, fillOpacity: 1,
        }).addTo(map).bindTooltip(name);
      }
    }
  }

  // home base
  L.marker([home.lat, home.lng], {
    icon: L.divIcon({ className: "home-pin", html: "🏠", iconSize: [24, 24] }),
  }).addTo(map).bindTooltip(home.name, { permanent: false });

  buildLegend(transit);
  return map;
}

function buildLegend(transit) {
  const rows = [];
  for (const line of Object.values(transit)) {
    if (line.kind === "subway") {
      rows.push(`<div class="lrow"><span class="swatch" style="background:${line.color}"></span>${line.name}</div>`);
    }
  }
  rows.push(`<div class="lrow"><span class="swatch dash"></span>key Davis buses (87/88/89/94/96)</div>`);
  rows.push(`<div class="lrow muted" style="margin-top:.4rem">● job — color = fit score</div>`);
  $("#legend").innerHTML = `<h4>Getting there</h4>${rows.join("")}`;
}

// --------------------------------------------------------------------------- //
// radius filter: circle around home, jobs outside it are hidden
// --------------------------------------------------------------------------- //
const RADIUS_KEY = "jobhunt_radius";

function loadRadiusPref() {
  try {
    const saved = JSON.parse(localStorage.getItem(RADIUS_KEY) || "null");
    if (saved) {
      state.radius.on = !!saved.on;
      const m = +saved.miles;
      if (m >= 0.5 && m <= 10) state.radius.miles = m;
    }
  } catch { /* corrupt pref -> defaults */ }
}

function saveRadiusPref() {
  localStorage.setItem(RADIUS_KEY, JSON.stringify({ on: state.radius.on, miles: state.radius.miles }));
}

function milesBetween(lat1, lng1, lat2, lng2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * 3958.8 * Math.asin(Math.sqrt(a));
}

// With the filter on: remote jobs stay, placed jobs must be inside the circle,
// and jobs with no known location are hidden (the backend resolves town names
// and even company addresses, so "unknown" now genuinely means unknowable).
function withinRadius(job) {
  if (!state.radius.on || job.remote) return true;
  if (job.lat == null) return false;
  return milesBetween(state.home.lat, state.home.lng, job.lat, job.lng) <= state.radius.miles;
}

function updateRadiusCircle() {
  const r = state.radius;
  if (!state.map) return;
  if (!r.on) {
    if (r.circle) { state.map.removeLayer(r.circle); r.circle = null; }
    return;
  }
  const meters = r.miles * 1609.344;
  if (r.circle) {
    r.circle.setRadius(meters);
  } else {
    r.circle = L.circle([state.home.lat, state.home.lng], {
      radius: meters, color: "#2563eb", weight: 1.5, dashArray: "6 6",
      fillColor: "#2563eb", fillOpacity: 0.05, interactive: false,
    }).addTo(state.map);
  }
}

// spread markers that resolve to the same coordinate so they don't stack
function jitter(lat, lng, seen) {
  const key = lat.toFixed(4) + "," + lng.toFixed(4);
  const n = seen.get(key) || 0;
  seen.set(key, n + 1);
  if (n === 0) return [lat, lng];
  const ang = n * 2.399963;                 // golden-angle spiral
  const r = 0.0006 * Math.sqrt(n);          // ~60m steps
  return [lat + r * Math.cos(ang), lng + r * Math.sin(ang)];
}

// --------------------------------------------------------------------------- //
// resizable list/map splitter
// --------------------------------------------------------------------------- //
function wireGutter() {
  const gutter = $("#gutter");
  const layout = document.querySelector(".layout");
  if (!gutter || !layout) return;

  const saved = localStorage.getItem("jobhunt_map_w");
  if (saved) layout.style.setProperty("--map-w", saved);

  let dragging = false, raf = 0;
  const onMove = (e) => {
    if (!dragging) return;
    const rect = layout.getBoundingClientRect();
    let w = rect.right - e.clientX;                  // map width = distance to right edge
    const max = rect.width - 320 - 240 - 12;         // keep room for sidebar + list + handle
    w = Math.max(300, Math.min(max, w));
    layout.style.setProperty("--map-w", w + "px");
    if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (state.map) state.map.invalidateSize(); });
  };
  const onUp = () => {
    if (!dragging) return;
    dragging = false;
    gutter.classList.remove("dragging");
    document.body.classList.remove("col-resizing");
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    const v = layout.style.getPropertyValue("--map-w");
    if (v) localStorage.setItem("jobhunt_map_w", v);
    if (state.map) state.map.invalidateSize();
  };
  gutter.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    dragging = true;
    gutter.classList.add("dragging");
    document.body.classList.add("col-resizing");
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  });
  gutter.addEventListener("dblclick", () => {        // reset to default split
    layout.style.removeProperty("--map-w");
    localStorage.removeItem("jobhunt_map_w");
    if (state.map) state.map.invalidateSize();
  });
}

// --------------------------------------------------------------------------- //
// rendering: jobs
// --------------------------------------------------------------------------- //
// "today" / "yesterday" / "3 days ago" from an ISO timestamp, or "" if absent.
function agoLabel(iso) {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (!(days >= 0)) return "";
  return days === 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

function jobCard(job) {
  const el = document.createElement("article");
  el.className = "job";
  el.dataset.id = job.id;

  let geoTag;
  if (job.lat != null) geoTag = `<span class="geo-tag">📍 ${job.geo}</span>`;
  else if (job.remote) geoTag = `<span class="geo-tag">🖥️ remote</span>`;
  else geoTag = `<span class="geo-tag none">📍 location unknown</span>`;

  // When first seen, and whether it keeps getting reposted (a live signal that
  // the opening is still actively hiring).
  const seen = agoLabel(job.first_seen);
  const seenTag = seen ? `<span class="age-tag" title="first seen ${escapeAttr(job.first_seen)}">🕑 ${seen}</span>` : "";
  const repostTag = job.repost_count > 0
    ? `<span class="repost-tag" title="posted again ${job.repost_count} more time${job.repost_count === 1 ? "" : "s"} since — still hiring">🔁 reposted ${job.repost_count}×</span>`
    : "";

  // Why this score: the keyword/location matches that added up to it.
  const reasons = (job.reasons || []).filter((r) => r.pts);
  const reasonsRow = reasons.length
    ? `<div class="reasons">${reasons.map((r) =>
        `<span class="why ${r.pts > 0 ? "up" : "down"}">${r.pts > 0 ? "+" : ""}${r.pts} ${escapeHtml(r.label)}</span>`
      ).join("")}</div>`
    : "";

  // Applied cards show how long ago; after a quiet stretch, nudge a follow-up.
  let appliedLine = "";
  if (job.status === "applied" && job.applied_at) {
    const days = Math.floor((Date.now() - new Date(job.applied_at).getTime()) / 86400000);
    if (days >= 0) {
      const ago = days === 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
      appliedLine = `<div class="applied-line">✅ Applied ${ago}${
        days >= FOLLOWUP_DAYS
          ? ` — no reply yet? <button class="linklike followup" type="button">Send a follow-up</button>`
          : ""}</div>`;
    }
  }

  el.innerHTML = `
    <div class="score" style="background:${scoreColor(job.score)}" title="fit score — higher is a better match" aria-label="fit score ${job.score}">${job.score}</div>
    <div class="body">
      <a class="title" href="${escapeAttr(job.url)}" target="_blank" rel="noopener">${escapeHtml(job.title)}</a>
      <div class="meta">${escapeHtml([job.company, job.location, job.source].filter(Boolean).join(" · "))}</div>
      <div class="summary">${escapeHtml(job.summary)}</div>
      ${reasonsRow}
      <div class="row">
        <button class="btn intg ${job.status === "interested" ? "on" : ""}" type="button">★ Interested</button>
        <button class="btn notg ${job.status === "rejected" ? "on" : ""}" type="button">✕ Not interested</button>
        <button class="btn apply" type="button">Apply</button>
        ${contactTag(job.contact_kind)}
        ${job.pay ? `<span class="pay-tag">💰 ${escapeHtml(job.pay)}</span>` : ""}
        ${geoTag}
        ${seenTag}
        ${repostTag}
      </div>
      ${appliedLine}
    </div>`;

  el.querySelector(".apply").addEventListener("click", (e) => { e.stopPropagation(); openComposer(job.id); });
  const fu = el.querySelector(".followup");
  if (fu) fu.addEventListener("click", (e) => { e.stopPropagation(); openComposer(job.id, "followup"); });
  el.querySelector(".intg").addEventListener("click", (e) => {
    e.stopPropagation();
    setStatus(job, job.status === "interested" ? "new" : "interested");
  });
  el.querySelector(".notg").addEventListener("click", (e) => {
    e.stopPropagation();
    setStatus(job, job.status === "rejected" ? "new" : "rejected");
  });
  el.querySelector(".title").addEventListener("click", (e) => e.stopPropagation());

  el.addEventListener("click", () => focusJob(job.id));
  return el;
}

function focusJob(id) {
  document.querySelectorAll(".job.active").forEach((n) => n.classList.remove("active"));
  const card = document.querySelector(`.job[data-id="${id}"]`);
  if (card) { card.classList.add("active"); card.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
  state.active = id;
  const m = state.markers.get(id);
  if (m) { state.map.flyTo(m.getLatLng(), Math.max(state.map.getZoom(), 14), { duration: .4 }); m.openPopup(); }
}

// --------------------------------------------------------------------------- //
// keyboard triage: fly through the list without the mouse
// --------------------------------------------------------------------------- //
function currentJob() {
  const jobs = (state.jobsData && state.jobsData.jobs) || [];
  return jobs.find((j) => j.id === state.active) || null;
}

function moveFocus(delta) {
  const cards = [...document.querySelectorAll(".job")];
  if (!cards.length) return;
  let idx = cards.findIndex((c) => c.dataset.id === state.active);
  idx = idx < 0 ? (delta > 0 ? 0 : cards.length - 1)
                : Math.max(0, Math.min(cards.length - 1, idx + delta));
  focusJob(cards[idx].dataset.id);
}

function wireKeyboard() {
  document.addEventListener("keydown", (e) => {
    // never hijack typing, shortcuts, or keys while a modal is open
    const t = e.target;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    if (!$("#overlay").hidden) return;

    const key = e.key.toLowerCase();
    if (key === "j" || key === "arrowdown") { e.preventDefault(); return moveFocus(1); }
    if (key === "k" || key === "arrowup") { e.preventDefault(); return moveFocus(-1); }

    const job = currentJob();
    if (!job) { if (["i", "x", "a", "o"].includes(key)) moveFocus(1); return; }
    if (key === "i") { e.preventDefault(); setStatus(job, job.status === "interested" ? "new" : "interested", true); }
    else if (key === "x") { e.preventDefault(); setStatus(job, job.status === "rejected" ? "new" : "rejected", true); }
    else if (key === "a") { e.preventDefault(); openComposer(job.id); }
    else if (key === "o") { e.preventDefault(); if (job.url) window.open(job.url, "_blank", "noopener"); }
  });
}

function renderJobs(data) {
  const list = $("#joblist");
  list.innerHTML = "";
  // clear old job markers
  for (const m of state.markers.values()) state.map.removeLayer(m);
  state.markers.clear();

  const jobs = data.jobs.filter(withinRadius);
  const hiddenJobs = data.jobs.filter((j) => !withinRadius(j));
  const unknown = hiddenJobs.filter((j) => j.lat == null).length;
  const outside = hiddenJobs.length - unknown;
  $("#resultCount").textContent = `${jobs.length} listing${jobs.length === 1 ? "" : "s"} shown` +
    (outside ? ` · ${outside} outside radius` : "") +
    (unknown ? ` · ${unknown} location unknown` : "");
  renderCounts(data.counts);
  renderTabs(data.counts);

  if (!jobs.length) {
    if (hiddenJobs.length) {
      list.innerHTML = `<div class="empty">All ${hiddenJobs.length} listing${hiddenJobs.length === 1 ? " here is" : "s here are"} outside your ${state.radius.miles} mi radius or in an unknown location.<br>Widen the radius or turn it off to see them.</div>`;
      return;
    }
    const v = VIEWS.find((x) => x.key === state.view);
    list.innerHTML = `<div class="empty">Nothing in <b>${escapeHtml(v ? v.label : state.view)}</b> yet.${
      (state.view === "new" || state.view === "latest") ? "<br>Hit <b>Fetch new jobs</b> to pull listings." : ""}</div>`;
    return;
  }

  const seen = new Map();
  for (const job of jobs) {
    list.appendChild(jobCard(job));
    if (job.lat != null) {
      const [lat, lng] = jitter(job.lat, job.lng, seen);
      const m = L.circleMarker([lat, lng], {
        radius: 6 + Math.min(8, Math.max(0, job.score) / 3),
        color: "#fff", weight: 1.5, fillColor: scoreColor(job.score), fillOpacity: .9,
      }).addTo(state.map);
      m.bindPopup(
        `<div class="popup-title">${escapeHtml(job.title)}</div>` +
        `<div class="popup-meta">${escapeHtml([job.company, job.location].filter(Boolean).join(" · "))} · score ${job.score}</div>` +
        `<a href="${escapeAttr(job.url)}" target="_blank" rel="noopener">Open listing →</a>`
      );
      m.on("click", () => focusJob(job.id));
      state.markers.set(job.id, m);
    }
  }
}

function renderCounts(counts) {
  const order = ["new", "interested", "applied", "rejected", "archived"];
  const el = $("#counts");
  el.innerHTML = order
    .filter((s) => counts[s])
    .map((s) => `<span class="count-pill">${s} <b>${counts[s]}</b></span>`)
    .join("");
}

function renderTabs(counts) {
  // 'all' sums the triage statuses only -- 'latest' overlaps them, so excluding
  // it here keeps the All badge from double-counting the last fetch's jobs.
  const total = ["new", "interested", "applied", "rejected", "archived"]
    .reduce((a, s) => a + (counts[s] || 0), 0);
  const n = (k) => (k === "all" ? total : (counts[k] || 0));
  const el = $("#tabs");
  el.innerHTML = VIEWS.map((v) =>
    `<button class="tab ${state.view === v.key ? "active" : ""}" data-view="${v.key}">${v.label}<span class="n">${n(v.key)}</span></button>`
  ).join("");
  el.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => { state.view = t.dataset.view; loadJobs(); }));
}

async function setStatus(job, status, advance = false) {
  // When advancing (keyboard triage), remember where this card sat so focus can
  // land on whatever slides into its place after the list reloads.
  let idx = -1;
  if (advance) {
    const cards = [...document.querySelectorAll(".job")];
    idx = cards.findIndex((c) => c.dataset.id === job.id);
  }
  try {
    await api.post("/api/mark", { id: job.id, status });
    const msg = { new: "Moved back to review", interested: "★ Added to Interested",
                  rejected: "Moved to Not interested" }[status] || ("Marked " + status);
    toast(msg);
    await loadJobs();
    if (advance && idx >= 0) {
      const cards = [...document.querySelectorAll(".job")];
      if (cards.length) focusJob(cards[Math.min(idx, cards.length - 1)].dataset.id);
    }
  } catch (e) { toast("Error: " + e.message); }
}

// --------------------------------------------------------------------------- //
// rendering: keywords
// --------------------------------------------------------------------------- //
function renderKeywords(stateData) {
  renderChips("#kwPositive", "positive", stateData.positive, "good", true);
  renderChips("#kwNegative", "negative", stateData.negative, "warn", true);
  renderChips("#kwExclude", "exclude", stateData.exclude, "bad", false);
}

function renderChips(sel, listName, data, cls, weighted) {
  const box = $(sel);
  box.innerHTML = "";
  const entries = weighted ? Object.entries(data) : data.map((t) => [t, null]);
  if (!entries.length) { box.innerHTML = `<span class="hint" style="margin:0">none yet</span>`; return; }
  for (const [term, pts] of entries.sort((a, b) => a[0].localeCompare(b[0]))) {
    const chip = document.createElement("span");
    chip.className = `chip ${cls}`;
    chip.innerHTML =
      `<span>${escapeHtml(term)}</span>` +
      (weighted ? `<span class="pts">${pts > 0 ? "+" : ""}${pts}</span>` : "") +
      `<button title="remove" aria-label="remove ${escapeAttr(term)}">✕</button>`;
    chip.querySelector("button").addEventListener("click", async () => {
      try {
        const s = await api.post("/api/keywords", { list: listName, action: "remove", term });
        renderKeywords(s);
        if (listName === "exclude") loadJobs();   // un-hide jobs that matched it
      } catch (e) { toast("Error: " + e.message); }
    });
    box.appendChild(chip);
  }
}

// --------------------------------------------------------------------------- //
// rendering: resume
// --------------------------------------------------------------------------- //
function humanSize(n) {
  n = n || 0;
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
  return (n / 1048576).toFixed(1) + " MB";
}

async function loadResume() {
  try { renderResume(await api.get("/api/resume")); }
  catch (e) { $("#resume").innerHTML = `<p class="hint">Couldn’t load resume: ${escapeHtml(e.message)}</p>`; }
}

function wireDrop(el) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drag"); });
  el.addEventListener("dragleave", () => el.classList.remove("drag"));
  el.addEventListener("drop", (e) => {
    e.preventDefault(); el.classList.remove("drag");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) uploadResume(e.dataTransfer.files[0]);
  });
}

function renderResume(data) {
  const box = $("#resume");
  const r = data.resume;
  if (!r) {
    box.innerHTML = `<div class="dropzone" id="dz"><span class="big">📄</span>
      Upload your resume<small>PDF, DOCX, or TXT · drag &amp; drop or click</small></div>`;
    const dz = $("#dz");
    dz.addEventListener("click", () => $("#resumeInput").click());
    wireDrop(dz);
    return;
  }
  const sugg = data.suggestions || [];
  let suggHtml = "";
  if (r.ext === ".pdf" && !r.extracted) {
    suggHtml = `<p class="warn-note">Couldn’t read text from this PDF. Add keywords manually,
      or upload a .docx / .txt to get suggestions.</p>`;
  } else if (sugg.length) {
    suggHtml = `<div class="suggest-wrap"><h3>Suggested good-fit keywords</h3>
      <div class="chips">` +
      sugg.map((t) => `<span class="chip suggest" data-term="${escapeAttr(t)}"><span class="plus">+</span> ${escapeHtml(t)}</span>`).join("") +
      `</div></div>`;
  } else if (r.extracted) {
    suggHtml = `<p class="hint" style="margin-top:.6rem">No new keyword suggestions from this resume.</p>`;
  }
  box.innerHTML = `
    <div class="resume-file">
      <div class="ficon">📄</div>
      <div>
        <div class="fname">${escapeHtml(r.filename)}</div>
        <div class="fmeta">${humanSize(r.size)} · ${escapeHtml((r.uploaded || "").replace("T", " "))}</div>
      </div>
    </div>
    <div class="resume-actions">
      <a class="btn tiny" href="${DEMO ? "#" : "/api/resume/file"}">Download</a>
      <button class="btn tiny" id="replaceBtn">Replace</button>
      <button class="btn tiny" id="delBtn">Delete</button>
    </div>${suggHtml}`;
  $("#replaceBtn").addEventListener("click", () => $("#resumeInput").click());
  $("#delBtn").addEventListener("click", deleteResume);
  box.querySelectorAll(".chip.suggest").forEach((c) =>
    c.addEventListener("click", () => addSuggestion(c.dataset.term)));
  wireDrop(box);
}

async function uploadResume(file) {
  if (!file) return;
  toast("Uploading " + file.name + "…", 4000);
  try {
    const res = await fetch("/api/resume?name=" + encodeURIComponent(file.name),
      { method: "POST", body: file });
    const j = await res.json();
    if (!res.ok) throw new Error(j.error || res.statusText);
    renderResume(j);
    toast(j.resume && j.resume.extracted && (j.suggestions || []).length
      ? `Resume uploaded — ${j.suggestions.length} keyword suggestion${j.suggestions.length === 1 ? "" : "s"}`
      : "Resume uploaded");
  } catch (e) { toast("Upload failed: " + e.message); }
}

async function addSuggestion(term) {
  try {
    const s = await api.post("/api/keywords", { list: "positive", action: "add", term });
    renderKeywords(s);
    await loadResume();                 // drop the now-added suggestion
    toast(`Added “${term}” to good fit`);
  } catch (e) { toast("Error: " + e.message); }
}

async function deleteResume() {
  if (!confirm("Remove your resume?")) return;
  try { renderResume(await api.post("/api/resume/delete", {})); toast("Resume removed"); }
  catch (e) { toast("Error: " + e.message); }
}

// --------------------------------------------------------------------------- //
// modal + apply composer + settings + outbox
// --------------------------------------------------------------------------- //
function contactTag(kind) {
  if (!kind) return "";
  const label = { email: "✉ email", form_only: "form", relay_only: "CL reply", none: "no email" }[kind] || kind;
  return `<span class="ctag ${kind}">${label}</span>`;
}

function openModal(html) {
  $("#modal").innerHTML = html;
  $("#overlay").hidden = false;
}
function closeModal() { $("#overlay").hidden = true; $("#modal").innerHTML = ""; }

// close on backdrop click / Esc
document.addEventListener("click", (e) => { if (e.target.id === "overlay") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function modalShell(title, sub, bodyHtml) {
  return `
    <div class="modal-head">
      <div><h2>${escapeHtml(title)}</h2>${sub ? `<div class="sub">${escapeHtml(sub)}</div>` : ""}</div>
      <button class="modal-x" id="mClose" aria-label="close">✕</button>
    </div>
    <div class="modal-body">${bodyHtml}</div>`;
}

// ---- Apply composer ----
async function openComposer(id, mode) {
  openModal(modalShell(mode === "followup" ? "Follow up" : "Apply", "", `<p class="hint">Loading…</p>`));
  $("#mClose").addEventListener("click", closeModal);
  try {
    const c = await api.get("/api/apply/compose?id=" + encodeURIComponent(id) +
                            (mode ? "&mode=" + encodeURIComponent(mode) : ""));
    renderComposer(c);
  } catch (e) { toast("Error: " + e.message); closeModal(); }
}

function renderComposer(c) {
  const job = c.job;
  const k = c.contact && c.contact.kind;
  const hasEmail = !!(c.contact && c.contact.email);
  const isRelay = k === "relay_only";
  // For a Craigslist reply-relay listing the user can paste the relay address,
  // so the compose fields are shown even though no email was auto-found. A
  // follow-up always composes (the address prefills from the original send).
  const showCompose = hasEmail || isRelay || !!c.followup;
  const applyUrl = (c.contact && c.contact.apply_url) || job.url;

  // contact section
  let contactHtml;
  if (!c.contact) {
    contactHtml = `<div class="contact-box">
      <div class="kindline">How to apply isn’t known yet.</div>
      <button class="btn tiny" id="scanBtn">🔎 Scan listing for contact info</button>
      <div class="muted-note">Fetches this one listing to look for an email / phone / apply link.</div>
    </div>`;
  } else if (k === "email") {
    contactHtml = `<div class="contact-box">
      <div class="kindline">${contactTag("email")} <span>Email found on the listing</span></div>
      <div>✉ <span class="cval">${escapeHtml(c.contact.email)}</span></div>
      ${c.contact.phone ? `<div>📞 ${escapeHtml(c.contact.phone)}</div>` : ""}
    </div>`;
  } else if (isRelay) {
    contactHtml = `<div class="contact-box">
      <div class="kindline">${contactTag(k)} <span>Craigslist hides the poster’s email — but you can still apply from here:</span></div>
      <ol class="relay-steps">
        <li><a href="${escapeAttr(applyUrl)}" target="_blank" rel="noopener">Open the listing ↗</a> and click <b>reply</b>.</li>
        <li>Copy the address that looks like <b>abc12-…@reply.craigslist.org</b>.</li>
        <li>Paste it into <b>To</b> below — Craigslist forwards your email to the poster.</li>
      </ol>
      ${c.contact.phone ? `<div>📞 ${escapeHtml(c.contact.phone)}</div>` : ""}
    </div>`;
  } else {
    contactHtml = `<div class="contact-box">
      <div class="kindline">${contactTag(k)} <span>This listing routes to an application form — apply on the site.</span></div>
      <div><a href="${escapeAttr(applyUrl)}" target="_blank" rel="noopener">${escapeHtml(applyUrl)}</a></div>
      ${c.contact.phone ? `<div>📞 ${escapeHtml(c.contact.phone)}</div>` : ""}
    </div>`;
  }

  // resume attach line
  const attachHtml = c.resume
    ? `<div class="attach-line">📎 ${escapeHtml(c.resume.filename)} will be attached</div>`
    : `<div class="attach-line warn">⚠ No resume uploaded — add one in the sidebar to attach it.</div>`;

  // action buttons gated by what's available
  const canSend = showCompose && c.smtp_configured && c.resume;
  const actions = [];
  if (showCompose) {
    actions.push(`<button class="btn primary" id="sendBtn" ${canSend ? "" : "disabled"}>Send with resume</button>`);
    actions.push(`<button class="btn" id="draftBtn">Open email draft</button>`);
  }
  actions.push(`<button class="btn" id="openBtn">Open application page</button>`);

  let gateNote = "";
  if (showCompose && !c.smtp_configured)
    gateNote = `<div class="muted-note">To send directly with your resume attached, set up your email in <a href="#" id="toSettings">Settings</a>. Or use “Open email draft”.</div>`;
  else if (showCompose && !c.resume)
    gateNote = `<div class="muted-note">Upload a resume to enable direct send.</div>`;

  const body = `
    ${contactHtml}
    ${showCompose ? `
    <div class="field"><label>To</label><input type="text" id="cTo" value="${escapeAttr(c.to)}" placeholder="${isRelay && !c.to ? "paste the …@reply.craigslist.org address here" : ""}"></div>
    <div class="field"><label>Subject</label><input type="text" id="cSubject" value="${escapeAttr(c.subject)}"></div>
    <div class="field"><label>Cover note</label><textarea id="cBody">${escapeHtml(c.body)}</textarea></div>
    ${attachHtml}` : ""}
    <div class="modal-actions">${actions.join("")}</div>
    ${gateNote}
    <div class="muted-note">Applications are sent one at a time, from your own email, and marked <b>applied</b> here.</div>`;

  openModal(modalShell(`${c.followup ? "Follow up" : "Apply"} · ${job.title}`,
    [job.company, job.location].filter(Boolean).join(" · "), body));
  $("#mClose").addEventListener("click", closeModal);

  const scan = $("#scanBtn");
  if (scan) scan.addEventListener("click", async () => {
    scan.disabled = true; scan.textContent = "Scanning…";
    try {
      await api.post("/api/contact", { id: job.id });
      const fresh = await api.get("/api/apply/compose?id=" + encodeURIComponent(job.id) +
                                  (c.followup ? "&mode=followup" : ""));
      renderComposer(fresh);
      loadJobs();                       // refresh card contact tags
    } catch (e) { toast("Scan failed: " + e.message); scan.disabled = false; scan.textContent = "🔎 Scan listing for contact info"; }
  });

  const ts = $("#toSettings");
  if (ts) ts.addEventListener("click", (e) => { e.preventDefault(); openSettings(); });

  const get = (id) => $("#" + id) ? $("#" + id).value : "";
  const sendBtn = $("#sendBtn");
  if (sendBtn) sendBtn.addEventListener("click", async () => {
    const to = get("cTo").trim();
    if (!to) return toast(isRelay ? "Paste the reply address from Craigslist into “To” first." : "Add a recipient address first.");
    if (!confirm(`Send your application to ${to} with ${c.resume.filename} attached?`)) return;
    sendBtn.disabled = true; sendBtn.textContent = "Sending…";
    try {
      await api.post("/api/apply/send", { id: job.id, to, subject: get("cSubject"), body: get("cBody") });
      toast("Application sent to " + to); closeModal(); loadJobs();
    } catch (e) { toast("Send failed: " + e.message); sendBtn.disabled = false; sendBtn.textContent = "Send with resume"; }
  });

  const draftBtn = $("#draftBtn");
  if (draftBtn) draftBtn.addEventListener("click", async () => {
    const to = get("cTo").trim();
    if (!to) return toast(isRelay ? "Paste the reply address from Craigslist into “To” first." : "Add a recipient address first.");
    try {
      const r = await api.post("/api/apply/draft", { id: job.id, to, subject: get("cSubject"), body: get("cBody") });
      window.location.href = r.mailto;   // open the user's mail client
      toast("Opened email draft — attach your resume and send"); closeModal(); loadJobs();
    } catch (e) { toast("Error: " + e.message); }
  });

  $("#openBtn").addEventListener("click", async () => {
    try {
      const r = await api.post("/api/apply/open", { id: job.id });
      window.open(r.url, "_blank", "noopener");
      toast("Opened the application page — marked applied"); closeModal(); loadJobs();
    } catch (e) { toast("Error: " + e.message); }
  });
}

// ---- Settings (profile + cover template + SMTP) ----
async function openSettings() {
  let p;
  try { p = await api.get("/api/profile"); } catch (e) { return toast("Error: " + e.message); }
  const a = p.applicant, s = p.smtp;
  const body = `
    <div class="row2">
      <div class="field"><label>Your name</label><input type="text" id="pName" value="${escapeAttr(a.name)}"></div>
      <div class="field"><label>Your email</label><input type="email" id="pEmail" value="${escapeAttr(a.email)}"></div>
    </div>
    <div class="field"><label>Phone</label><input type="text" id="pPhone" value="${escapeAttr(a.phone)}"></div>
    <div class="field"><label>Cover note template <span class="hint">— {job_title} {company} {name} {my_email} {my_phone}</span></label>
      <textarea id="pTemplate">${escapeHtml(p.cover_template)}</textarea></div>
    <hr style="border:none;border-top:1px solid var(--line);margin:1rem 0">
    <h3 style="margin:.2rem 0 .5rem;font-size:.95rem">Email sending (optional)</h3>
    <p class="muted-note" style="margin-top:0">To send applications with your resume attached, use your own email. For Gmail: host <b>smtp.gmail.com</b>, port <b>587</b>, and an <b>App Password</b> (not your normal password). Stored only on this machine.</p>
    <div class="row2">
      <div class="field"><label>SMTP host</label><input type="text" id="sHost" value="${escapeAttr(s.host)}" placeholder="smtp.gmail.com"></div>
      <div class="field"><label>Port</label><input type="number" id="sPort" value="${escapeAttr(s.port)}"></div>
    </div>
    <div class="field"><label>SMTP username</label><input type="text" id="sUser" value="${escapeAttr(s.user)}" placeholder="you@gmail.com"></div>
    <div class="field"><label>Password / App Password ${s.configured ? "<span class='hint'>— leave blank to keep current</span>" : ""}</label>
      <input type="password" id="sPass" placeholder="${s.configured ? "•••••••• (unchanged)" : ""}"></div>
    <div class="field"><label>From name (optional)</label><input type="text" id="sFrom" value="${escapeAttr(s.from_name)}"></div>
    <div class="smtp-status ${s.configured ? "ok" : ""}" id="smtpStatus">${s.configured ? "✓ email is set up" : ""}</div>
    <div class="modal-actions">
      <button class="btn primary" id="saveBtn">Save</button>
      <button class="btn" id="testBtn">Send test connection</button>
    </div>`;
  openModal(modalShell("Settings", "Your info, cover note, and email setup", body));
  $("#mClose").addEventListener("click", closeModal);

  const smtpPayload = () => ({
    host: $("#sHost").value, port: $("#sPort").value, user: $("#sUser").value,
    password: $("#sPass").value, from_name: $("#sFrom").value,
  });
  const profilePayload = () => ({
    applicant: { name: $("#pName").value, email: $("#pEmail").value, phone: $("#pPhone").value },
    cover_template: $("#pTemplate").value,
    smtp: smtpPayload(),
  });

  $("#saveBtn").addEventListener("click", async () => {
    try { await api.post("/api/profile", profilePayload()); toast("Settings saved"); closeModal(); }
    catch (e) { toast("Error: " + e.message); }
  });
  $("#testBtn").addEventListener("click", async () => {
    const st = $("#smtpStatus");
    st.className = "smtp-status"; st.textContent = "Testing…";
    try {
      const r = await api.post("/api/smtp/test", { smtp: smtpPayload() });
      st.className = "smtp-status " + (r.ok ? "ok" : "bad");
      st.textContent = (r.ok ? "✓ " : "✕ ") + r.message;
    } catch (e) { st.className = "smtp-status bad"; st.textContent = "✕ " + e.message; }
  });
}

// ---- Outbox ----
async function openOutbox() {
  let d;
  try { d = await api.get("/api/applications"); } catch (e) { return toast("Error: " + e.message); }
  const rows = d.applications;
  const body = rows.length ? `<div class="outbox">` + rows.map((a) => `
    <div class="outbox-row">
      <span class="mth">${escapeHtml(a.method)}</span>
      <div>
        <div class="ojob">${escapeHtml(a.title || a.job_id || "")}${a.company ? " · " + escapeHtml(a.company) : ""}</div>
        <div class="odate">${escapeHtml((a.created_at || "").replace("T", " "))}${a.to_addr ? " · " + escapeHtml(a.to_addr) : ""}${a.error ? " · " + escapeHtml(a.error) : ""}</div>
      </div>
      <span class="st-${escapeAttr(a.status)}">${escapeHtml(a.status)}</span>
    </div>`).join("") + `</div>`
    : `<div class="empty">No applications yet.</div>`;
  openModal(modalShell("Sent applications", `${rows.length} logged`, body));
  $("#mClose").addEventListener("click", closeModal);
}

// --------------------------------------------------------------------------- //
// in-app updates
// --------------------------------------------------------------------------- //
function fmtVersion(v) {
  if (!v || !v.sha) return "unknown version";
  return `${(v.date || "").slice(0, 10)} · ${v.sha.slice(0, 7)}`;
}

// One-shot toast for the result of the last update (written during restart).
async function showUpdateResult() {
  try {
    const s = await api.get("/api/update/status");
    if (!s.result) return;
    if (s.result.status === "updated") {
      toast(`✓ Updated to version ${fmtVersion(s.current)}`, 5000);
    } else if (s.result.status === "rolled_back") {
      toast("⚠ The update didn't start correctly, so the previous version was restored.", 8000);
    }
  } catch { /* endpoint may not exist mid-migration */ }
}

// Always-visible version line at the bottom of the sidebar: shows the installed
// version, doubles as a manual "check again", and links to the update when one
// is ready. The topbar button is the loud indicator; this is the quiet one.
function renderVersionLine(info) {
  const el = $("#versionLine");
  el.hidden = false;
  if (info.container) {
    el.innerHTML = `Version ${escapeHtml(fmtVersion(info.current))} · container ` +
      `<span title="Update by pulling a new image (see the update script)">· update by rebuilding the image</span>`;
    return;
  }
  const cur = escapeHtml(fmtVersion(info.current)) + (info.git ? " · git" : "");
  if (info.available) {
    el.innerHTML = `Version ${cur} · <button class="linklike vl-new" type="button">` +
      `⬆ a new version is ready — install it</button>`;
    el.querySelector("button").addEventListener("click", () => openUpdateModal(info));
  } else {
    el.innerHTML = `Version ${cur} · ✓ up to date · ` +
      `<button class="linklike" type="button">check again</button>`;
    el.querySelector("button").addEventListener("click", () => {
      toast("Checking for updates…");
      checkForUpdate(true);
    });
  }
}

async function checkForUpdate(force = false) {
  let info;
  try { info = await api.get("/api/update/check" + (force ? "?force=1" : "")); }
  catch (e) {
    if (force) toast("Couldn't check for updates: " + e.message, 5000);
    return;
  }
  renderVersionLine(info);
  const btn = $("#updateBtn");
  btn.hidden = !info.available;
  if (!info.available) {
    if (force) toast("✓ You're on the latest version");
    return;
  }
  btn.onclick = () => openUpdateModal(info);
  if (force) openUpdateModal(info);
}

function openUpdateModal(info) {
  const notes = (info.notes || []).length
    ? `<div class="update-notes"><h3>What's new</h3><ul>` +
      info.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("") + `</ul></div>`
    : (info.first_update
        ? `<p class="hint">This install predates version tracking, so there's no change list yet — after this update you'll always see what's new.</p>`
        : "");
  const body = `
    <p>A new version of jobhunt is ready.</p>
    <div class="update-vers">
      <span>You have: <b>${escapeHtml(fmtVersion(info.current))}</b></span>
      <span>Latest: <b>${escapeHtml(fmtVersion(info.latest))}</b></span>
    </div>
    ${notes}
    <div class="modal-actions">
      <button class="btn primary" id="updNow">Update now</button>
      <button class="btn" id="updLater">Not now</button>
    </div>
    <div class="muted-note">${info.git
      ? "Git checkout — Update now runs <b>git pull --ff-only</b> and restarts. Uncommitted local changes will block it."
      : "Your saved jobs, settings, resume, and email login are never touched by an update."}</div>`;
  openModal(modalShell("Update jobhunt", "", body));
  $("#mClose").addEventListener("click", closeModal);
  $("#updLater").addEventListener("click", closeModal);
  $("#updNow").addEventListener("click", applyUpdate);
}

async function applyUpdate() {
  const btn = $("#updNow");
  btn.disabled = true;
  btn.textContent = "Updating…";
  let r;
  try { r = await api.post("/api/update/apply", {}); }
  catch (e) {
    toast("Update failed: " + e.message, 6000);
    btn.disabled = false;
    btn.textContent = "Update now";
    return;
  }
  if (!r.restarting) {
    // Old launcher (no supervisor yet): the files are updated, but the running
    // server can't restart itself. One manual restart finishes the migration.
    openModal(modalShell("Update installed ✓", "", `
      <p>One last step to finish this update:</p>
      <ol class="relay-steps">
        <li><b>Close the little jobhunt window</b> (the black text window).</li>
        <li><b>Double-click your usual start file</b> to open jobhunt again.</li>
      </ol>
      <p class="hint">Future updates finish on their own — this extra step is one time only.</p>`));
    $("#mClose").addEventListener("click", closeModal);
    return;
  }
  openModal(modalShell("Updating…", "", `
    <p>Installing the new version and restarting. This page reloads by itself
    in a few seconds.</p>`));
  waitForRestart();
}

async function waitForRestart() {
  const start = Date.now();
  let sawDown = false;
  while (Date.now() - start < 90000) {
    await new Promise((res) => setTimeout(res, 1000));
    try {
      const r = await fetch("/api/state");
      // Ignore replies from the old process (it exits ~1s after answering);
      // reload once the server has gone down and come back.
      if (r.ok && (sawDown || Date.now() - start > 20000)) return location.reload();
    } catch { sawDown = true; }
  }
  location.reload();   // last resort -- let the page show whatever state exists
}

// --------------------------------------------------------------------------- //
// wiring
// --------------------------------------------------------------------------- //
async function loadJobs() {
  const min = $("#minScore").value;
  const data = await api.get(`/api/jobs?view=${encodeURIComponent(state.view)}&min_score=${min}`);
  state.jobsData = data;
  renderJobs(data);
}

// re-apply client-side filters (radius) without refetching
function rerenderJobs() {
  if (state.jobsData) renderJobs(state.jobsData);
}

function wireKeywordForms() {
  document.querySelectorAll(".kw-add").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const listName = form.dataset.list;
      const term = form.querySelector("input[type=text]").value.trim();
      if (!term) return;
      const body = { list: listName, action: "add", term };
      const w = form.querySelector(".weight");
      if (w) body.weight = parseInt(w.value, 10) || 0;
      try {
        const s = await api.post("/api/keywords", body);
        form.querySelector("input[type=text]").value = "";
        renderKeywords(s);
        if (listName === "exclude") { loadJobs(); toast("Excluded — hidden from the list"); }
        else toast("Saved — applies on next fetch");
      } catch (err) { toast("Error: " + err.message); }
    });
  });
}

async function doFetch() {
  const btn = $("#fetchBtn");
  const label = btn.querySelector(".btn-label");
  btn.disabled = true;
  btn.querySelector(".spinner").hidden = false;
  label.textContent = "Fetching…";

  // Fetch runs in the background now; the demo has no backend to poll, so it
  // keeps the old one-shot call (which the demo rejects politely).
  if (DEMO) {
    try { await api.post("/api/fetch", {}); }
    catch (e) { toast(e.message); }
    finally {
      btn.disabled = false; btn.querySelector(".spinner").hidden = true;
      label.textContent = "Fetch new jobs";
    }
    return;
  }

  try {
    await api.post("/api/fetch", {});
    // Poll progress and show the latest step on the button until it finishes.
    while (true) {
      await new Promise((r) => setTimeout(r, 1000));
      let st;
      try { st = await api.get("/api/fetch/status"); } catch { continue; }
      const last = st.lines && st.lines[st.lines.length - 1];
      if (last) label.textContent = last.length > 22 ? last.slice(0, 21) + "…" : last;
      if (st.running) continue;
      if (st.error) { toast("Fetch failed: " + st.error); break; }
      const s = st.summary || { total_new: 0, per_source: {} };
      const errs = Object.entries(s.per_source || {}).filter(([, v]) => typeof v === "string");
      toast(`${s.total_new} new listing${s.total_new === 1 ? "" : "s"}` +
            (errs.length ? ` (${errs.map(([k]) => k).join(", ")} had issues)` : ""));
      if (s.total_new > 0) state.view = "latest";
      await loadJobs();
      break;
    }
  } catch (e) {
    toast("Fetch failed: " + e.message);
  } finally {
    btn.disabled = false;
    btn.querySelector(".spinner").hidden = true;
    label.textContent = "Fetch new jobs";
  }
}

async function init() {
  const s = await api.get("/api/state");
  state.transit = s.transit;
  state.home = s.home;
  state.statuses = s.statuses;

  // min-score default from config
  const ms = $("#minScore");
  ms.value = s.min_display_score ?? 1;
  $("#minScoreVal").textContent = ms.value;

  state.map = initMap(s.home, s.transit);
  wireGutter();
  wireKeyboard();
  renderKeywords(s);
  wireKeywordForms();

  $("#resumeInput").addEventListener("change", (e) => {
    if (e.target.files[0]) uploadResume(e.target.files[0]);
    e.target.value = "";
  });
  loadResume();

  ms.addEventListener("input", () => { $("#minScoreVal").textContent = ms.value; });
  ms.addEventListener("change", loadJobs);

  // radius filter: restore saved pref, then keep circle + list in sync
  loadRadiusPref();
  const rOn = $("#radiusOn"), rSlider = $("#radius");
  rOn.checked = state.radius.on;
  rSlider.value = state.radius.miles;
  rSlider.disabled = !state.radius.on;
  $("#radiusVal").textContent = state.radius.miles;
  updateRadiusCircle();
  rOn.addEventListener("change", () => {
    state.radius.on = rOn.checked;
    rSlider.disabled = !rOn.checked;
    saveRadiusPref();
    updateRadiusCircle();
    rerenderJobs();
  });
  rSlider.addEventListener("input", () => {
    state.radius.miles = +rSlider.value;
    $("#radiusVal").textContent = rSlider.value;
    saveRadiusPref();
    updateRadiusCircle();
    rerenderJobs();
  });
  $("#fetchBtn").addEventListener("click", doFetch);
  $("#settingsBtn").addEventListener("click", openSettings);
  $("#outboxBtn").addEventListener("click", openOutbox);

  if (DEMO) {
    $("#homeLabel").textContent = "live demo · sample Davis-area data";
    document.querySelector(".brand h1").insertAdjacentHTML("beforeend",
      ' <span class="demo-badge">DEMO</span>');
    toast("Demo — explore freely. Fetch & email sending are off in the demo.", 5000);
  } else if (!s.adzuna_ready) {
    toast("Tip: add free Adzuna keys to the config for local distance filtering", 5000);
  }
  if (!DEMO) {
    showUpdateResult();
    checkForUpdate();
    // keep looking while the app sits open, so a new version shows up
    // without needing a page refresh
    setInterval(checkForUpdate, 5 * 60 * 1000);
  }
  await loadJobs();
  setTimeout(() => state.map.invalidateSize(), 200);
}

// --------------------------------------------------------------------------- //
// DEMO backend — serves the baked snapshot, mutates an in-memory copy so the
// page is fully clickable with no server. Live-only actions reject politely.
// --------------------------------------------------------------------------- //
let demoStore = null;
function demoEnsure() {
  if (demoStore || !DEMO_DATA) return;
  demoStore = {
    state: DEMO_DATA.state,
    jobs: DEMO_DATA.jobs.map((j) => ({ ...j })),
    resume: DEMO_DATA.resume,
    profile: DEMO_DATA.profile,
    applications: (DEMO_DATA.applications || []).slice(),
  };
}
const DEMO_LIVE_ONLY = "This runs in the full app — the demo is read-only here.";

function demoGet(path) {
  demoEnsure();
  const [p, qs] = path.split("?");
  const params = new URLSearchParams(qs || "");
  if (p === "/api/state") return Promise.resolve(demoStore.state);
  if (p === "/api/jobs") return Promise.resolve(demoJobsView(params.get("view"), +(params.get("min_score") || 0)));
  if (p === "/api/resume") return Promise.resolve(demoStore.resume);
  if (p === "/api/profile") return Promise.resolve(demoStore.profile);
  if (p === "/api/applications") return Promise.resolve({ applications: demoStore.applications });
  if (p === "/api/apply/compose") return Promise.resolve(demoCompose(params.get("id"), params.get("mode")));
  return Promise.reject(new Error("demo: unknown " + p));
}

function demoHasTerm(term, text) {                 // word-boundary match (mirrors backend)
  if (!term) return false;
  const e = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp("(?<![a-z0-9])" + e + "(?![a-z0-9])").test(text);
}
function demoExcluded(j) {
  const terms = demoStore.state.exclude || [];
  if (!terms.length) return false;
  const hay = [j.title, j.company, j.location, j.summary].map((x) => x || "").join(" ").toLowerCase();
  return terms.some((t) => demoHasTerm(t.toLowerCase(), hay));
}
function demoJobsView(view, minScore) {
  const VS = { new: "new", interested: "interested", applied: "applied", rejected: "rejected" };
  const st = VS[view];
  const all = demoStore.jobs.filter((j) => j.score >= (minScore || 0) && !demoExcluded(j));
  const counts = {};
  for (const j of all) counts[j.status] = (counts[j.status] || 0) + 1;
  // Newest first_seen stamp = the last fetch batch (mirrors the Python backend).
  const latest = all.reduce((m, j) => (j.first_seen && (!m || j.first_seen > m)) ? j.first_seen : m, null);
  const latestJobs = latest ? all.filter((j) => j.first_seen === latest) : [];
  counts.latest = latestJobs.length;
  if (view === "latest") return { jobs: latestJobs, counts };
  return { jobs: all.filter((j) => !st || j.status === st), counts };
}

const DEMO_FOLLOWUP_TMPL =
  "Hi,\n\nI applied for the {job_title} position recently and wanted to check in — " +
  "I'm still very interested. I've attached my resume again in case it's helpful. " +
  "Is there anything else you need from me?\n\nThanks so much,\n{name}\n{my_email} | {my_phone}\n";

function demoCompose(id, mode) {
  const followup = mode === "followup";
  const j = demoStore.jobs.find((x) => x.id === id) || {};
  const appl = demoStore.profile.applicant || {};
  let c = null;
  if (j.contact_kind && j._contact) {
    c = { kind: j._contact.kind, email: (j._contact.emails || [])[0] || null,
          phone: (j._contact.phones || [])[0] || null, apply_url: j._contact.apply_url || j.url };
  }
  const tail = appl.name ? " - " + appl.name : "";
  const subj = followup
    ? `Following up on my application: ${j.title || "your opening"}${tail}`
    : `Application: ${j.title || "your opening"}${tail}`;
  return {
    job: { id: j.id, title: j.title, company: j.company, url: j.url, source: j.source, location: j.location },
    followup,
    contact: c,
    resume: demoStore.resume.resume ? { filename: demoStore.resume.resume.filename } : null,
    applicant: { name: appl.name || "", email: appl.email || "", phone: appl.phone || "" },
    smtp_configured: false,
    to: (c && c.email) || "",
    subject: subj,
    body: demoCover(followup ? DEMO_FOLLOWUP_TMPL : (demoStore.profile.cover_template || ""), j, appl),
  };
}
function demoCover(tmpl, job, appl) {
  const f = { name: appl.name || "", my_email: appl.email || "", my_phone: appl.phone || "",
              job_title: job.title || "the role", company: job.company || "your team" };
  return tmpl.replace(/\{(\w+)\}/g, (_, k) => (k in f ? f[k] : ""));
}

function demoLog(method, body, status) {
  const j = demoStore.jobs.find((x) => x.id === body.id);
  demoStore.applications.unshift({
    id: demoStore.applications.length + 1, job_id: body.id, method,
    to_addr: body.to || null, subject: body.subject || null, attachment: null,
    status, error: null, created_at: "just now (demo)",
    title: j ? j.title : "", company: j ? j.company : "",
  });
}

function demoPost(path, body) {
  demoEnsure();
  if (path === "/api/mark") {
    const j = demoStore.jobs.find((x) => x.id === body.id);
    if (j) j.status = body.status;
    return Promise.resolve({ ok: true });
  }
  if (path === "/api/keywords") {
    const s = demoStore.state, term = (body.term || "").toLowerCase();
    if (body.list === "exclude") {
      s.exclude = s.exclude || [];
      if (body.action === "add") { if (!s.exclude.includes(term)) s.exclude.push(term); }
      else s.exclude = s.exclude.filter((t) => t !== term);
    } else {
      const key = body.list === "positive" ? "positive" : "negative";
      s[key] = s[key] || {};
      if (body.action === "add") s[key][term] = body.weight ?? (body.list === "positive" ? 4 : -4);
      else delete s[key][term];
    }
    return Promise.resolve(s);
  }
  if (path === "/api/contact") {
    const j = demoStore.jobs.find((x) => x.id === body.id);
    const info = (j && j._contact) || { emails: [], phones: [], apply_url: j ? j.url : "", kind: "none" };
    if (j) j.contact_kind = info.kind;
    return Promise.resolve(info);
  }
  if (path === "/api/apply/draft") {
    const j = demoStore.jobs.find((x) => x.id === body.id);
    if (j) j.status = "applied";
    demoLog("mailto", body, "drafted");
    return Promise.resolve({ mailto: `mailto:${encodeURIComponent(body.to || "")}?subject=${encodeURIComponent(body.subject || "")}&body=${encodeURIComponent(body.body || "")}` });
  }
  if (path === "/api/apply/open") {
    const j = demoStore.jobs.find((x) => x.id === body.id);
    if (j) j.status = "applied";
    demoLog("open_page", body, "opened");
    return Promise.resolve({ url: (j && j.url) || "#" });
  }
  if (path === "/api/profile") {
    Object.assign(demoStore.profile.applicant, body.applicant || {});
    if ("cover_template" in body) demoStore.profile.cover_template = body.cover_template;
    return Promise.resolve(demoStore.profile);
  }
  return Promise.reject(new Error(DEMO_LIVE_ONLY));
}

// --------------------------------------------------------------------------- //
// escaping
// --------------------------------------------------------------------------- //
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

init().catch((e) => { document.body.insertAdjacentHTML("beforeend",
  `<div class="empty">Failed to start: ${escapeHtml(e.message)}</div>`); });
