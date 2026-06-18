# ASX Mood Index

A Fear & Greed–style market-sentiment gauge for the Australian market, built *in
the method of* the CNN Business Fear & Greed Index and calibrated to the ASX. A
single 0–100 score where 0 is maximum fear and 100 is maximum greed.

It is a **sentiment gauge, not a trading signal** — it measures market mood, makes
no forecast, and should never be framed as a buy/sell or timing instrument.

**Status:** Phase 0 (free MVP) — the engine, four no-key components, compositing
and labelling, with a test suite. Phase 1 adds the two breadth components from a
licensed full-universe feed.

---

## What's built (Phase 0)

Four components, all from free, redistribution-clean sources, run through a single
shared normalisation engine:

| Component | Raw signal | Direction | Source |
|---|---|---|---|
| Momentum | XJO vs its 125-day SMA | high = greed | free XJO close |
| Volatility | 20-day realised vol of XJO returns | high = fear (inverted) | free XJO close |
| Safe haven | 20-day equity return − 20-day bond return | high = greed | XJO + RBA F2 |
| AUD | 20-day AUD/USD momentum | high = greed | RBA F11.1 |

The normalisation engine (`src/asx_mood/normalise.py`) is the spine: each raw
signal is z-scored against its own trailing 252-day history, clipped to [−3, +3],
and mapped linearly to 0–100 (z = 0 → 50). Fear-positive signals (volatility) are
inverted. The composite is the equal-weighted mean of the component scores.

## Quick start

```bash
python -m pip install -e .            # or: pip install pandas numpy requests pytest
python -m pytest -q                   # run the test suite

# Offline demo — synthetic inputs, no network needed:
PYTHONPATH=src python -m asx_mood.cli --source synthetic

# Live — needs network access to the RBA and a free XJO host (see below):
PYTHONPATH=src python -m asx_mood.cli --source live --json reading.json --history history.csv
```

## Front end

A dependency-free static dashboard lives in `web/` (vanilla HTML/CSS/SVG, no build
step, no CDN libraries). It renders the gauge, the component breakdown and a
trailing-history chart from the JSON the CLI emits.

```bash
# 1. Generate the data file the page reads (live or synthetic):
PYTHONPATH=src python -m asx_mood.cli --source live --json web/data.json

# 2. Serve the directory and open it:
python -m http.server --directory web 8137   # -> http://localhost:8137
```

The page loads `web/data.json` if present and otherwise falls back to the
committed `web/data.sample.json`, so it renders out of the box. `web/data.json`
is gitignored (it's generated; the sample is the only committed data file). The
JSON schema is exactly the CLI's `--json` output: `{date, score, label,
components, history[]}`. When the Cloudflare build lands, the scheduled Worker
writes that same JSON shape and the Pages front end serves this `web/` directory
unchanged.

## Running with live data

`--source live` fetches:
- **XJO daily closes** from a free source (Stooq, Yahoo fallback) — `data/xjo.py`
- **AUD/USD** from RBA table F11.1 — `data/rba.py`
- **10y CGS yield** from RBA table F2 — `data/rba.py`

**If the free APIs are blocked** (Stooq now serves a JavaScript anti-bot page and
Yahoo rate-limits with HTTP 429), download an `^AXJO` daily CSV in your browser
and pass it directly — the most reliable path:

```bash
# Yahoo: finance.yahoo.com/quote/%5EAXJO/history -> Download
# (or Stooq's site download). Then:
PYTHONPATH=src python -m asx_mood.cli --source live --xjo-csv ~/Downloads/^AXJO.csv --json web/data.json
```

The CSV parser accepts both Yahoo (`Date,...,Close,Adj Close,...`) and Stooq
(`Date,...,Close,Volume`) download formats.

In a **restricted cloud session** these hosts must be on the environment's network
egress allowlist, otherwise the fetch returns HTTP 403:

```
www.rba.gov.au
stooq.com
query1.finance.yahoo.com   # only if using the Yahoo fallback
```

Run locally and they just work. The loaders also accept a local CSV / parsed text
so you can run fully offline from a downloaded copy.

## Methodology notes & deliberate deviations from the spec

These follow the pre-build review and are applied in code:

1. **Breadth uses a McClellan *oscillator*, not a raw running summation.** A
   cumulative summation is non-stationary, so a 252-day z-score of its *level* is
   ill-defined. The oscillator (19/39-day EMA difference of net advancing volume)
   is stationary and z-scores cleanly. (`components.mcclellan_oscillator`,
   used in Phase 1.)
2. **Display bands are calibrated to the composite's own history.** Averaging
   several components shrinks the composite's variance toward 50, so the naive
   fixed 0–100 cutoffs rarely reach the extremes. Labels default to the
   composite's historical percentiles; pass `--fixed-bands` for the spec's fixed
   cutoffs. (`composite.label_calibrated`.)
3. **XJO licensing flagged.** The XJO index level is itself an S&P/ASX licensed
   product. Phase 0 uses a free XJO source for internal validation only; before
   public display this must be resolved (display only *derived* values, or move
   the market proxy to the STW ETF / a self-computed basket). See `data/xjo.py`.
4. **Bond leg states its duration assumption.** The RBA 10y series is a yield, not
   a tradeable price; we synthesise a carry + duration price return with a stated
   modified duration (~8). (`components.bond_total_return`.)

## Project layout

```
src/asx_mood/
  normalise.py     # z-score engine: rolling z -> clip -> 0..100 -> invert
  components.py    # raw-signal calculations (Phase 0 + Phase 1 breadth)
  composite.py     # equal-weighted composite, labels, Reading dataclass
  index.py         # Phase 0 orchestration: inputs -> scores -> composite
  cli.py           # command-line runner (synthetic | live)
  data/
    __init__.py    # multi-source calendar alignment
    rba.py         # RBA F11.1 (AUD/USD) and F2 (10y CGS yield) loaders
    xjo.py         # free XJO close loaders (Stooq / Yahoo)
    synthetic.py   # offline synthetic inputs for the demo + tests
tests/             # engine, components, parser, compositing
```

## Roadmap

- **Phase 1 — full six components.** Add a licensed full-ASX-universe EOD feed
  (e.g. EODHD commercial plan) to compute stock-price strength (52-week highs/lows)
  and volume breadth in-house. Apply a liquidity filter to the universe and use
  point-in-time constituents (incl. delisted) for any backfill, to avoid
  survivorship bias. **Confirm redistribution rights in writing first.**
- **Phase 2 — refinements.** Historical backfill (“where are we vs the last
  year”), a published methodology page, an optional materials-sector component,
  and a more responsive volatility window. Deploy as a scheduled job + static
  front end.

## Compliance framing

Describe the tool only as a market-mood / sentiment gauge (RG 234 general-advice
boundary), publish the methodology and chosen windows, attribute RBA data, and do
not re-display the A-VIX or any S&P index value. Get actual legal/compliance
sign-off rather than relying on framing alone.
