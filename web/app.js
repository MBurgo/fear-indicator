"use strict";

// Five band colours, fear/headwind -> greed/tailwind. The band *edges* are
// calibrated from the index's own history and supplied in the JSON (bandEdges);
// these colours and the default edges are the only presentation constants.
const BAND_COLORS = ["#c0392b", "#e67e22", "#b8a93a", "#2ecc71", "#1f9d57"];
const DEFAULT_EDGES = [25, 45, 55, 75];
const DEFAULT_LABELS = ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"];

const COMPONENT_LABELS = {
  // ASX Mood Index
  momentum: "Momentum",
  strength: "Stock strength",
  breadth: "Volume breadth",
  safe_haven: "Safe haven",
  volatility: "Volatility",
  aud: "AUD risk flow",
  // ASX Drivers Index
  commodity: "Commodity complex",
  curve_slope: "Yield-curve slope",
  credit_risk: "Global credit risk",
  short_positioning: "Short positioning",
  china: "China momentum",
};

const SVG_NS = "http://www.w3.org/2000/svg";

// Build [{min,max,label,color}] bands from four ascending edges + five labels.
function makeBands(edges, labels) {
  const e = edges && edges.length === 4 ? edges : DEFAULT_EDGES;
  const names = labels && labels.length === 5 ? labels : DEFAULT_LABELS;
  const bounds = [0, ...e, 100];
  return BAND_COLORS.map((color, i) => ({
    min: bounds[i],
    max: bounds[i + 1],
    label: names[i],
    color,
  }));
}

function bandForScore(score, bands) {
  return bands.find((b) => score >= b.min && score < b.max) || bands[bands.length - 1];
}

function colorForScore(score, bands) {
  return bandForScore(score, bands).color;
}

function el(name, attrs) {
  const node = document.createElementNS(SVG_NS, name);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  return node;
}

// Point on an upper semicircle (y grows downward in screen space).
function polar(cx, cy, r, angleDeg) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}

// Map a 0..100 score onto the dial: 0 -> 180deg (left), 100 -> 0deg (right).
function scoreToAngle(score) {
  return 180 - (Math.max(0, Math.min(100, score)) / 100) * 180;
}

function arcPath(cx, cy, r, startScore, endScore) {
  const start = polar(cx, cy, r, scoreToAngle(startScore));
  const end = polar(cx, cy, r, scoreToAngle(endScore));
  return `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${end.x} ${end.y}`;
}

function renderGauge(score, bands, lowLabel, highLabel) {
  const svg = document.getElementById("gauge");
  svg.innerHTML = "";
  const cx = 200, cy = 210, r = 160, stroke = 26;

  for (const band of bands) {
    svg.appendChild(el("path", {
      d: arcPath(cx, cy, r, band.min, band.max),
      fill: "none",
      stroke: band.color,
      "stroke-width": stroke,
      "stroke-linecap": "butt",
      opacity: "0.85",
    }));
  }

  const left = polar(cx, cy, r + 24, scoreToAngle(2));
  const right = polar(cx, cy, r + 24, scoreToAngle(98));
  const fearTxt = el("text", { x: left.x, y: left.y, "text-anchor": "start" });
  fearTxt.textContent = "0 " + (lowLabel || "Fear");
  const greedTxt = el("text", { x: right.x, y: right.y, "text-anchor": "end" });
  greedTxt.textContent = (highLabel || "Greed") + " 100";
  for (const t of [fearTxt, greedTxt]) {
    t.setAttribute("fill", "#8b98a5");
    t.setAttribute("font-size", "13");
    svg.appendChild(t);
  }

  const tip = polar(cx, cy, r - 10, scoreToAngle(score));
  svg.appendChild(el("line", {
    x1: cx, y1: cy, x2: tip.x, y2: tip.y,
    stroke: "#e6edf3", "stroke-width": "4", "stroke-linecap": "round",
  }));
  svg.appendChild(el("circle", { cx, cy, r: "10", fill: "#e6edf3" }));
  svg.appendChild(el("circle", { cx, cy, r: "4", fill: "#0f1419" }));
}

function renderReadout(data, bands) {
  const score = data.score;
  document.getElementById("gauge-score").textContent = score;
  const labelNode = document.getElementById("gauge-label");
  labelNode.textContent = data.label || bandForScore(score, bands).label;
  labelNode.style.color = colorForScore(score, bands);
  if (data.date) {
    document.getElementById("gauge-date").textContent = "As of " + data.date;
  }
}

// A legend of the calibrated bands, highlighting the current one.
function renderBandLegend(bands, score) {
  const root = document.getElementById("band-legend");
  if (!root) return;
  root.innerHTML = "";
  const current = bandForScore(score, bands);
  for (const band of bands) {
    const chip = document.createElement("div");
    chip.className = "band-chip" + (band === current ? " active" : "");
    const dot = document.createElement("span");
    dot.className = "band-dot";
    dot.style.background = band.color;
    const txt = document.createElement("span");
    const lo = Math.round(band.min);
    const hi = Math.round(band.max);
    txt.textContent = `${band.label} (${lo}–${hi})`;
    chip.append(dot, txt);
    root.appendChild(chip);
  }
}

function renderSummary(summary) {
  const root = document.getElementById("summary");
  if (!root) return;
  root.textContent = summary || "";
  root.style.display = summary ? "block" : "none";
}

function renderComponents(components, bands) {
  const root = document.getElementById("components");
  root.innerHTML = "";
  for (const key of Object.keys(components)) {
    const val = components[key];
    const row = document.createElement("div");
    row.className = "component";

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = COMPONENT_LABELS[key] || key;

    const track = document.createElement("div");
    track.className = "track";
    const fill = document.createElement("div");
    fill.className = "fill";
    fill.style.width = Math.max(0, Math.min(100, val)) + "%";
    fill.style.background = colorForScore(val, bands);
    track.appendChild(fill);

    const v = document.createElement("div");
    v.className = "val";
    v.textContent = Math.round(val);

    row.append(name, track, v);
    root.appendChild(row);
  }
}

function renderHistory(history, bands) {
  const svg = document.getElementById("history");
  svg.innerHTML = "";
  if (!history || history.length < 2) return;

  const w = 820, h = 260, padL = 34, padR = 12, padT = 12, padB = 24;
  const innerW = w - padL - padR, innerH = h - padT - padB;
  const n = history.length;

  const x = (i) => padL + (i / (n - 1)) * innerW;
  const y = (s) => padT + (1 - s / 100) * innerH;

  for (const band of bands) {
    svg.appendChild(el("rect", {
      x: padL, y: y(band.max), width: innerW, height: y(band.min) - y(band.max),
      fill: band.color, opacity: "0.08",
    }));
  }

  for (const s of [0, 50, 100]) {
    svg.appendChild(el("line", {
      x1: padL, y1: y(s), x2: w - padR, y2: y(s),
      stroke: "#2d3742", "stroke-width": "1",
    }));
    const t = el("text", { x: padL - 6, y: y(s) + 4, "text-anchor": "end", "font-size": "11", fill: "#8b98a5" });
    t.textContent = s;
    svg.appendChild(t);
  }

  const points = history.map((d, i) => `${x(i).toFixed(1)},${y(d.score).toFixed(1)}`).join(" ");
  svg.appendChild(el("polyline", {
    points, fill: "none", stroke: "#5aa9e6", "stroke-width": "2",
    "stroke-linejoin": "round", "stroke-linecap": "round",
  }));

  const last = history[n - 1];
  svg.appendChild(el("circle", {
    cx: x(n - 1), cy: y(last.score), r: "4", fill: colorForScore(last.score, bands),
    stroke: "#0f1419", "stroke-width": "1.5",
  }));

  const meta = document.getElementById("history-meta");
  meta.innerHTML = "";
  const from = document.createElement("span");
  from.textContent = history[0].date;
  const to = document.createElement("span");
  to.textContent = last.date + "  ·  " + history.length + " trading days";
  meta.append(from, to);
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
    if (data.title) {
      document.title = data.title;
      const h1 = document.querySelector(".head h1");
      if (h1) h1.textContent = data.title;
    }
    if (data.tagline) {
      const tag = document.querySelector(".tagline");
      if (tag) tag.textContent = data.tagline;
    }
    renderGauge(data.score, bands, data.lowLabel, data.highLabel);
    renderReadout(data, bands);
    renderBandLegend(bands, data.score);
    renderSummary(data.summary);
    renderComponents(data.components || {}, bands);
    renderHistory(data.history || [], bands);
    const note = document.getElementById("source-note");
    note.textContent = source === "data.sample.json"
      ? "Showing bundled sample data (data.sample.json). Generate data.json to see live values."
      : "Showing data.json.";
  } catch (err) {
    document.getElementById("gauge-label").textContent = "No data";
    document.getElementById("source-note").textContent = String(err.message || err);
  }
}

main();
