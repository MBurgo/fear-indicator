# ASX Drivers Index — Build Specification

*A free-to-source market gauge for Australian investors that measures whether the
forces driving Australian equities — commodities, the dollar, interest rates,
global credit risk, and short positioning — are currently a tailwind or a
headwind. Built on the same normalisation engine as the ASX Mood Index, but with
no licensed exchange-price dependency.*

**Version:** 1.0 (draft spec) · **Status:** Pre-build · **Owner:** Matt Burgess

---

## 1. Purpose and framing

The ASX Drivers Index is a single 0–100 score, where 0 means the external forces
that move Australian shares are maximally hostile (headwind) and 100 means they
are maximally supportive (tailwind). It is built for an Australian audience and
sourced entirely from free, redistribution-clean data.

### Why "drivers", not "mood"

The ASX 200 is structurally concentrated: financials and materials are roughly
half the index. Australian equity portfolios are, in aggregate, a leveraged bet
on a small set of external forces — commodity prices, the AUD, the interest-rate
curve, global risk appetite, and how aggressively the market is positioned short.
None of those require licensed ASX price data.

This is the key difference from the ASX Mood Index, which tried to measure
*sentiment from share prices* and therefore needed a licensed equity feed. By
measuring the **drivers** instead of the prices, this index sidesteps the
licensing wall entirely — and for a market this concentrated, the drivers are
arguably a truer read on what is actually moving people's holdings than a generic
sentiment dial would be.

### Honesty about what it is

This is an *indirect* gauge. It infers the climate for Australian equities from
their drivers; it does not measure share-price action directly. That is a genuine
trade-off, stated plainly here and to be stated on any public methodology page.
As with the ASX Mood Index, it is a **conditions gauge, not a trading signal**,
which is also the safer position under ASIC RG 234 (see §8).

---

## 2. The shared normalisation engine (reused)

This index reuses the ASX Mood Index engine unchanged. Each component's raw
signal is converted to a z-score against its own recent history, clipped, and
mapped to 0–100:

1. Compute the raw signal (per component, §3).
2. Trailing mean and standard deviation over a normalisation window.
3. `z = (current − mean) / std`.
4. Clip to `[−3, +3]`.
5. `score = 50 + (z_clipped / 3) × 50`.
6. Invert (`100 − score`) for headwind-positive signals (credit risk, short
   positioning).

Composite = equal-weighted mean of the available component scores, rounded for
display. The existing Python package (`asx_mood.normalise`, `asx_mood.composite`)
and the static front end (`web/`) carry over **without modification**, because the
output schema (`{date, score, label, components, history}`) is identical.

The one engine extension this index needs is **native-frequency normalisation
with as-of forward-fill** for the mixed-cadence inputs — see §5. That is additive;
it does not change the daily pipeline above.

### Label bands

Reuse the ASX Mood Index bands, and — as established in that project's review —
**calibrate the band cutoffs to the composite's own historical distribution**
rather than slicing 0–100 naively, because averaging components compresses the
composite toward 50. Suggested labels: Strong Headwind / Headwind / Neutral /
Tailwind / Strong Tailwind.

---

## 3. Component calculation logic

Five core components plus one optional overlay. Every series below is free and
carries no ASX/S&P exchange-licensing dependency.

### 3.1 Export commodity complex  ·  *daily + monthly*

**Raw signal:** momentum of a basket of Australia's principal export commodities.

**Basket (suggested weights, tune to export value):** iron ore (~35%), coal
(metallurgical + thermal, ~20%), gold (~15%), LNG (~15%), base metals
(aluminium / copper / nickel, ~15%).

**Calculation:** build a weighted commodity index from the basket, then take its
trailing momentum (e.g. index vs its 3-month average, or 63-trading-day rate of
change). High = tailwind (greed).

**Cadence:** gold is **daily** (LBMA London fix, also on FRED). Iron ore, coal,
LNG and base metals come from the **monthly** World Bank "Pink Sheet" (or IMF).
The basket is therefore mixed-frequency; it is computed at native frequency and
forward-filled per §5. Iron ore and coal implicitly carry the **Chinese
steel-demand** signal, which is why China is only an optional separate component
(§3.6).

**Why it belongs:** materials are ~20%+ of the ASX and the dominant swing factor;
the export complex is the single most Australian-specific equity driver there is.

### 3.2 AUD risk flow  ·  *daily*

**Raw signal:** 20-day momentum of AUD/USD (or the RBA trade-weighted index).

**Calculation:** `aud_raw = (AUD_today − AUD_20d_ago) / AUD_20d_ago`. High =
tailwind (greed).

**Cadence:** daily, RBA F11.1 (published next business day).

**Why it belongs:** the AUD is a textbook risk-on/commodity currency — it sells
off in global fear episodes and rallies on returning risk appetite, more cleanly
than most currencies.

### 3.3 Yield-curve slope  ·  *daily*

**Raw signal:** the slope of the Commonwealth Government bond curve, 10-year minus
2-year yield.

**Calculation:** `slope_raw = yield_10y − yield_2y` (percentage points). High
(steeper) = tailwind (greed); inversion = recession warning = headwind.

**Cadence:** daily, RBA F2.

**Why it belongs:** a steeper curve widens bank net-interest margins (financials
are the other ~half of the ASX) and supports equity valuations; an inverted curve
is a classic recession lead. Using the *slope* rather than the *level* gives a
clean directional reading, avoiding the "are falling yields good or bad?"
ambiguity of a raw-rate signal.

### 3.4 Global credit risk  ·  *daily*

**Raw signal:** the US high-yield corporate credit spread (ICE BofA US High Yield
Option-Adjusted Spread).

**Calculation:** `credit_raw = HY_OAS` (basis points). High/widening = global
risk-off = headwind, so this component is **inverted** at step 6.

**Cadence:** daily, FRED series `BAMLH0A0HYM2`.

**Why it belongs:** the ASX is high-beta to global risk appetite, and credit
spreads are the cleanest free expression of it. This also recovers the
"junk-bond demand" dimension the ASX Mood Index had to drop for lack of an
Australian high-yield market — it exists, free, for the US.

**Licensing note (mirrors the A-VIX decision in the Mood Index spec):** the
obvious "global fear" series is the **VIX**, but the VIX is a CBOE/S&P product and
public re-display of its values may carry the same licensing problem A-VIX did.
This spec therefore uses the **credit spread** as the global-risk input, which is
redistributable via FRED with attribution (confirm commercial terms per series).
The VIX may be eyeballed privately for sanity-checking but is **not** ingested or
displayed.

### 3.5 Short positioning  ·  *daily (T+4 lag)*

**Raw signal:** market-wide aggregate short interest across the liquid ASX
universe, from ASIC's short-position reports.

**Calculation:** for each liquid stock, ASIC reports the short position as a
percentage of total quantity on issue. Aggregate into a market-wide measure —
either the issued-capital-weighted average short percentage, or the median across
the liquid universe — and z-score its **level**. Rising aggregate short interest =
growing bearish positioning = headwind, so this component is **inverted**.

**Universe filter:** restrict to liquid names (ASX 200 / All Ordinaries members,
or a minimum issued-capital / turnover threshold). This avoids micro-cap noise —
the same liquidity-filter discipline flagged in the Mood Index review.

**Cadence:** ASIC publishes aggregated short positions **daily, with a ~4
business-day lag** (positions reported to ASIC are aggregated and released four
trading days later). Each datum must be stamped by its **publication date**, not
its reference date, so the index never uses information it could not have had
(§5).

**Interpretation caveat (state publicly):** short interest is *positioning*, not a
directional forecast. Some shorts are hedges or arbitrage, and crowded shorts can
precede squeezes (a contrarian tell). Treat it as a fear/positioning input, not a
prediction — consistent with "gauge, not signal."

**Why it belongs:** this is the one genuinely **equity-internal, Australian,
free, official** signal available. It is also novel — nobody packages aggregate
ASX short positioning for retail investors.

### 3.6 China momentum  ·  *monthly · optional overlay*

**Raw signal:** China manufacturing PMI (NBS official, or Caixin).

**Calculation:** PMI level relative to the 50 expansion/contraction line, or its
3-month momentum. High = tailwind (greed) for the materials complex.

**Cadence:** **monthly**, released on the first business day after month-end.

**Why it is optional:** China is Australia's dominant export market, but its
steel-demand signal is already substantially embedded in iron ore and coal
(§3.1). Including PMI separately risks double-counting. Ship the five core
components first; add China only if backtesting shows it adds independent signal.

---

## 4. Parameter summary

| Component | Raw signal | Direction | Native cadence | Normalisation window |
|---|---|---|---|---|
| Commodity complex | Weighted export basket, momentum | High = tailwind | gold daily; rest monthly | 252 d (daily legs) / 36 m (monthly legs) |
| AUD risk flow | AUD/USD 20-day momentum | High = tailwind | daily | 252 d |
| Yield-curve slope | 10y − 2y CGS yield | High = tailwind | daily | 252 d |
| Global credit risk | US HY OAS | High = headwind (invert) | daily | 252 d |
| Short positioning | Aggregate ASX short % | High = headwind (invert) | daily (T+4 lag) | 252 d |
| China momentum *(opt.)* | Manufacturing PMI | High = tailwind | monthly | 36 m |

All components: z-score clipped to `[−3, +3]`, mapped to 0–100, equal-weighted
into the composite. **Each component is normalised at its native frequency, then
its score is forward-filled onto the daily grid** (§5).

### Correlation honesty

As with the Mood Index, "six components" overstates the independent dimensions.
Commodities, the AUD, and global credit risk all load on a common global
risk-on/off factor; commodities and China overlap by construction. Equal
weighting remains the defensible default, but publish the component correlation
matrix and acknowledge that the effective weights are not equal. Short positioning
and the yield-curve slope are the most independent inputs.

---

## 5. Mixed-frequency handling (the core engineering detail)

The index refreshes **daily**, but two inputs (the commodity ex-gold legs and
China PMI) are **monthly**, and one (short positioning) is **daily but lagged**.
The rule that keeps this statistically honest:

> **Compute and normalise every component at its native frequency, then
> forward-fill the resulting 0–100 score onto the daily composite grid, stamped
> by the date the data was actually available.**

Three consequences follow.

**1. Do not compute daily changes on forward-filled monthly levels.** If you
forward-fill a monthly commodity price to daily and then take a daily return, you
get a spike on release day and zeros in between — a fabricated signal. Instead,
compute the momentum on the *monthly* series (month-over-month or 3-month change),
then forward-fill that signal.

**2. Normalise monthly series against a monthly window.** A 252-trading-day window
holds only ~12 monthly observations, and forward-filling makes the daily sample
look larger than it is (repeated values understate the standard deviation, which
inflates z-scores). Z-score monthly components against a **trailing window of
monthly observations** (suggest 36 months), then forward-fill the score. Never
z-score forward-filled monthly data at daily frequency.

**3. Use publication-date (point-in-time) stamping, never reference date.** The
Pink Sheet for month M is released in early M+1; PMI for month M on the first
business day of M+1; ASIC shorts at T+4. Each datum enters the daily series only
from its **availability date**. This prevents look-ahead and is essential for any
backfill to be credible (the same point-in-time discipline raised in the Mood
Index review). Maintain a small release-calendar / as-of map per source.

The daily composite on date *t* is therefore the equal-weighted mean of each
component's most recently *available* score as of *t*. Daily components update
every day; monthly components hold their last score until the next release;
short positioning lags four trading days.

---

## 6. Data source map

Every source below is free and carries no ASX/S&P exchange-licensing dependency —
the entire point of this design.

| Source | What it supplies | Cadence | Access |
|---|---|---|---|
| **RBA F11.1** | AUD/USD, trade-weighted index | daily | free CSV |
| **RBA F2** | 2y & 10y CGS yields | daily | free CSV |
| **FRED** | US HY OAS (`BAMLH0A0HYM2`); daily LBMA gold (`GOLDPMGBD228NLBM`) | daily | free API key |
| **World Bank "Pink Sheet" (CMO)** | iron ore, coal (Australian), LNG (Asia), aluminium, copper, nickel | monthly | free download |
| **IMF Primary Commodity Prices** | commodity price alternative / cross-check | monthly | free |
| **ASIC short-position reports** | aggregated short positions by stock (% on issue) | daily (T+4) | free CSV |
| **China NBS / Caixin PMI** *(optional)* | manufacturing PMI | monthly | free |

**Redistribution notes.** RBA and World Bank/IMF data are openly redistributable
with attribution. FRED is a free API; individual series carry their source's
terms — the ICE BofA OAS is redistributable via FRED with attribution, but
**confirm commercial-display terms per series** (and note the VIX is deliberately
excluded for the licensing reason in §3.4). ASIC reports are official government
data, redistribution-defensible with attribution. None of these is an
ASX/S&P-licensed price product.

**What is deliberately NOT used:** any ASX share price or index level (XJO, STW
price, A-VIX, VIX). The design needs none of them.

---

## 7. Build path

### Phase 0 — daily-only core (validate engine + new sources, zero spend)

Four fully-daily components, no mixed-frequency machinery yet:

- AUD risk flow — RBA F11.1
- Yield-curve slope — RBA F2
- Global credit risk — FRED HY OAS
- Commodity (gold leg only) — FRED daily gold

This proves the new data loaders and reuses the existing engine, composite, and
front end end-to-end. Only dependency is a free FRED API key (RBA is keyless).

### Phase 1 — full five-component index

Add the **mixed-frequency commodity complex** (World Bank monthly basket) and the
**ASIC short-positioning** component, plus the native-frequency normalisation and
as-of forward-fill machinery (§5). This is the complete index.

### Phase 2 — refinements

Optional China overlay (§3.6); point-in-time backfill using a per-source release
calendar (the most compelling way to present the gauge — "tailwind vs the last
year"); published methodology page; component-correlation disclosure.

### Stack (unchanged from the Mood Index)

Scheduled daily job → compute components → write `data.json` → static front end
renders the gauge and history. The Python engine (`asx_mood`) and the `web/`
dashboard are reused as-is; new work is confined to data loaders and the
native-frequency / as-of layer.

---

## 8. Compliance and framing checklist

- Describe the tool as a **market-conditions / drivers gauge**, never a buy/sell
  or timing signal (RG 234 general-advice boundary). Be explicit that it measures
  the *drivers* of Australian equities, not share prices or a price forecast.
- Publish the **methodology, the component windows, and the mixed-frequency
  handling** — transparency supports credibility and ASIC defensibility.
- Attribute every source (RBA, FRED/ICE, World Bank, IMF, ASIC) per its terms;
  **confirm FRED series' commercial-display terms** before launch.
- Do **not** ingest or display the VIX or any ASX/S&P-licensed price/index value;
  the credit-spread component removes the need.
- State the **short-interest interpretation caveat** (positioning, not a
  forecast; squeeze risk) wherever that component is surfaced.

---

## 9. Known limitations (state these honestly)

- **Indirect.** It reads the climate for Australian equities from their drivers,
  not from share prices. In an idiosyncratic local episode (e.g. a domestic
  banking shock with calm commodities), it can lag the actual market.
- **Mixed cadence.** Daily core, monthly commodity/China legs, T+4 short data.
  The gauge moves at blended speed; the §5 handling makes this honest but does not
  make the monthly legs fast.
- **Correlated inputs.** Commodities, AUD, and global credit risk share a common
  risk factor; equal weighting overstates independence (§4).
- **China data quality.** Official PMI is the weakest free input; hence optional.
- **Short-data lag.** The most equity-specific component is four trading days
  stale by construction.
