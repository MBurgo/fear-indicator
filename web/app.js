"use strict";

// Five band colours, headwind -> tailwind. The composite gauge uses the
// percentile band edges from the JSON (bandEdges); the component bars use a
// fixed raw 0-100 scale (RAW_EDGES) since they aren't compressed.
const BAND_COLORS = ["#c0392b", "#e67e22", "#b8a93a", "#2ecc71", "#1f9d57"];
const DEFAULT_EDGES = [25, 45, 55, 75];
const DEFAULT_LABELS = ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"];
const RAW_EDGES = [25, 45, 55, 75];

// Component score thresholds for the tailwind / headwind chip rows.
const TAILWIND_AT = 55;
const HEADWIND_AT = 45;

const COMPONENT_LABELS = {
  momentum: "Momentum", strength: "Stock strength", breadth: "Volume breadth",
  safe_haven: "Safe haven", volatility: "Volatility", aud: "AUD risk flow",
  commodity: "Commodity complex", curve_slope: "Yield-curve slope",
  credit_risk: "Global credit risk", short_positioning: "Short positioning",
  china: "China momentum",
};

const BAND_DESCRIPTIONS = {
  "Strong Headwind": "The forces driving Australian shares are strongly unfavourable — among the most hostile readings in the index's history.",
  "Headwind": "On balance, conditions are leaning against Australian equities.",
  "Neutral": "The drivers are broadly balanced — a typical reading, with no clear push either way.",
  "Tailwind": "On balance, conditions are leaning in favour of Australian equities.",
  "Strong Tailwind": "The forces driving Australian shares are strongly favourable — among the most supportive readings in the index's history.",
  "Extreme Fear": "Sentiment is deeply fearful — among the most fearful readings in the index's history.",
  "Fear": "Sentiment is leaning fearful.",
  "Greed": "Sentiment is leaning greedy.",
  "Extreme Greed": "Sentiment is intensely greedy — among the most greedy readings in the index's history.",
};

const SVG_NS = "http://www.w3.org/2000/svg";
const clamp = (v) => Math.max(0, Math.min(100, v));

function makeBands(edges, labels) {
  const e = edges && edges.length === 4 ? edges : DEFAULT_EDGES;
  const names = labels && labels.length === 5 ? labels : DEFAULT_LABELS;
  const bounds = [0, ...e, 100];
  return BAND_COLORS.map((color, i) => ({ min: bounds[i], max: bounds[i + 1], label: names[i], color }));
}

function bandForScore(score, bands) {
  return bands.find((b) => score >= b.min && score < b.max) || bands[bands.length - 1];
}
function colorForScore(score, bands) { return bandForScore(score, bands).color; }

function el(name, attrs) {
  const node = document.createElementNS(SVG_NS, name);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  return node;
}
function div(cls, text) {
  const d = document.createElement("div");
  if (cls) d.className = cls;
  if (text != null) d.textContent = text;
  return d;
}

// --- Gauge (semicircular dial) ---
function polar(cx, cy, r, deg) {
  const a = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}
const scoreToAngle = (s) => 180 - (clamp(s) / 100) * 180;
function arcPath(cx, cy, r, a, b) {
  const s = polar(cx, cy, r, scoreToAngle(a)), e = polar(cx, cy, r, scoreToAngle(b));
  return `M ${s.x} ${s.y} A ${r} ${r} 0 0 1 ${e.x} ${e.y}`;
}

function renderGauge(score, bands, lowLabel, highLabel) {
  const svg = document.getElementById("gauge");
  svg.innerHTML = "";
  const cx = 200, cy = 210, r = 160, stroke = 26;
  for (const band of bands) {
    svg.appendChild(el("path", {
      d: arcPath(cx, cy, r, band.min, band.max), fill: "none", stroke: band.color,
      "stroke-width": stroke, "stroke-linecap": "butt", opacity: "0.9",
    }));
  }
  // End labels, placed in the clear space below the arc for legibility.
  const lt = el("text", { x: 36, y: 238, "text-anchor": "start" });
  lt.textContent = "0 · " + (lowLabel || "Fear");
  const rt = el("text", { x: 364, y: 238, "text-anchor": "end" });
  rt.textContent = (highLabel || "Greed") + " · 100";
  for (const t of [lt, rt]) {
    t.setAttribute("fill", "#b7c2cd"); t.setAttribute("font-size", "14");
    t.setAttribute("font-family", "ui-monospace, monospace"); svg.appendChild(t);
  }
  const tip = polar(cx, cy, r - 10, scoreToAngle(score));
  svg.appendChild(el("line", { x1: cx, y1: cy, x2: tip.x, y2: tip.y, stroke: "#e6edf3", "stroke-width": "4", "stroke-linecap": "round" }));
  svg.appendChild(el("circle", { cx, cy, r: "10", fill: "#e6edf3" }));
  svg.appendChild(el("circle", { cx, cy, r: "4", fill: "#0f1419" }));
}

function renderReadout(data, bands) {
  const color = colorForScore(data.score, bands);
  const scoreNode = document.getElementById("gauge-score");
  scoreNode.textContent = data.score;
  scoreNode.style.color = color;
  const labelNode = document.getElementById("gauge-label");
  labelNode.textContent = data.label || bandForScore(data.score, bands).label;
  labelNode.style.color = color;
  document.getElementById("score-note").textContent = "50 = typical · vs its own history";
  if (data.date) document.getElementById("gauge-date").textContent = data.date;
}

// --- Horizontal band scale with a marker at the current score ---
function renderBandBar(score, label, bands) {
  const root = document.getElementById("band-bar");
  if (!root) return;
  root.innerHTML = "";

  const marker = div("bandbar-marker");
  marker.style.left = clamp(score) + "%";
  marker.appendChild(div("bandbar-mlabel mono", `${Math.round(score)} · ${label}`));
  marker.appendChild(div("bandbar-tri"));

  const track = div("bandbar-track");
  for (const b of bands) {
    const seg = div("bandbar-seg");
    seg.style.width = (b.max - b.min) + "%";
    seg.style.background = b.color;
    track.appendChild(seg);
  }

  const axis = div("bandbar-axis mono");
  const ticks = [...bands.map((b) => b.min), 100];
  for (const t of ticks) {
    const s = div(null, String(t));
    s.style.left = t + "%";
    axis.appendChild(s);
  }
  root.append(marker, track, axis);
}

// --- Tailwind / headwind chip rows ---
function chip(label, color) {
  const c = div("driver-chip");
  const dot = div("driver-dot");
  dot.style.background = color;
  c.append(dot, div("driver-name", label));
  return c;
}
function renderDrivers(components, rawBands) {
  const root = document.getElementById("drivers");
  if (!root) return;
  root.innerHTML = "";
  const tail = [], head = [];
  for (const k of Object.keys(components)) {
    const v = components[k];
    if (v >= TAILWIND_AT) tail.push([k, v]);
    else if (v <= HEADWIND_AT) head.push([k, v]);
  }
  const addRow = (title, items) => {
    if (!items.length) return;
    const row = div("driver-row");
    row.appendChild(div("driver-title mono " + (title === "TAILWINDS" ? "is-tail" : "is-head"), title));
    const chips = div("driver-chips");
    for (const [k, v] of items) chips.appendChild(chip(COMPONENT_LABELS[k] || k, colorForScore(v, rawBands)));
    row.appendChild(chips);
    root.appendChild(row);
  };
  addRow("TAILWINDS", tail);
  addRow("HEADWINDS", head);
}

// --- Components: diverging bars centred at 50 ---
function renderComponents(components, rawBands) {
  const root = document.getElementById("components");
  root.innerHTML = "";
  for (const key of Object.keys(components)) {
    const v = clamp(components[key]);
    const row = div("component");
    row.appendChild(div("name", COMPONENT_LABELS[key] || key));

    const track = div("track");
    track.appendChild(div("track-center"));
    const fill = div("fill");
    if (v >= 50) { fill.style.left = "50%"; fill.style.width = (v - 50) + "%"; }
    else { fill.style.left = v + "%"; fill.style.width = (50 - v) + "%"; }
    fill.style.background = colorForScore(v, rawBands);
    track.appendChild(fill);
    row.appendChild(track);

    row.appendChild(div("val", String(Math.round(components[key]))));
    root.appendChild(row);
  }
}

// --- History line chart ---
function renderHistory(history, bands) {
  const svg = document.getElementById("history");
  svg.innerHTML = "";
  if (!history || history.length < 2) return;
  const w = 820, h = 260, padL = 30, padR = 12, padT = 12, padB = 22;
  const innerW = w - padL - padR, innerH = h - padT - padB, n = history.length;
  const x = (i) => padL + (i / (n - 1)) * innerW;
  const y = (s) => padT + (1 - s / 100) * innerH;

  for (const band of bands) {
    svg.appendChild(el("rect", { x: padL, y: y(band.max), width: innerW, height: y(band.min) - y(band.max), fill: band.color, opacity: "0.07" }));
  }
  for (const s of [0, 50, 100]) {
    svg.appendChild(el("line", { x1: padL, y1: y(s), x2: w - padR, y2: y(s), stroke: "#2d3742", "stroke-width": "1" }));
    const t = el("text", { x: padL - 6, y: y(s) + 4, "text-anchor": "end", "font-size": "11", fill: "#8b98a5", "font-family": "ui-monospace, monospace" });
    t.textContent = s; svg.appendChild(t);
  }
  const pts = history.map((d, i) => `${x(i).toFixed(1)},${y(d.score).toFixed(1)}`).join(" ");
  svg.appendChild(el("polyline", { points: pts, fill: "none", stroke: "#5aa9e6", "stroke-width": "2", "stroke-linejoin": "round", "stroke-linecap": "round" }));
  const last = history[n - 1];
  svg.appendChild(el("circle", { cx: x(n - 1), cy: y(last.score), r: "4", fill: colorForScore(last.score, bands), stroke: "#0f1419", "stroke-width": "1.5" }));

  const meta = document.getElementById("history-meta");
  meta.innerHTML = "";
  meta.append(div(null, history[0].date), div(null, last.date + " · " + history.length + " trading days"));
}

async function loadData() {
  for (const url of ["data.json", "data.sample.json"]) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) return { data: await res.json(), source: url };
    } catch (_) { /* try next */ }
  }
  throw new Error("No data file found (data.json or data.sample.json).");
}

async function main() {
  try {
    const { data, source } = await loadData();
    const bands = makeBands(data.bandEdges, data.bandLabels);
    const rawBands = makeBands(RAW_EDGES, data.bandLabels);
    if (data.title) {
      document.title = data.title;
      const h1 = document.querySelector(".head h1");
      if (h1) h1.textContent = data.title;
    }
    if (data.tagline) {
      const tag = document.querySelector(".tagline");
      if (tag) tag.textContent = data.tagline;
    }
    const label = data.label || bandForScore(data.score, bands).label;
    renderGauge(data.score, bands, data.lowLabel, data.highLabel);
    renderReadout(data, bands);
    document.getElementById("band-description").textContent = BAND_DESCRIPTIONS[label] || "";
    renderBandBar(data.score, label, bands);
    renderDrivers(data.components || {}, rawBands);
    renderComponents(data.components || {}, rawBands);
    renderHistory(data.history || [], bands);
    document.getElementById("source-note").textContent =
      source === "data.sample.json" ? "Showing bundled sample data. Generate data.json for live values." : "";
  } catch (err) {
    document.getElementById("gauge-label").textContent = "No data";
    document.getElementById("source-note").textContent = String(err.message || err);
  }
}

main();
