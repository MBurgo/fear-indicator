"""FRED (St. Louis Fed) series loaders for the ASX Drivers Index.

Uses the keyless ``fredgraph.csv`` download endpoint rather than the API, so no
key is needed for Phase 0. FRED is an institutional source: script-friendly, no
anti-bot wall, no aggressive rate limiting for occasional CSV pulls (unlike the
free consumer-finance endpoints the ASX Mood Index struggled with).

Series used:
  BAMLH0A0HYM2        ICE BofA US High Yield Option-Adjusted Spread (daily, %)
  DCOILBRENTEU        Crude Oil Brent (daily, USD/bbl, EIA) - Phase 0 commodity leg

Phase 0 commodity note: gold's free daily FRED series (the LBMA fixings) was
discontinued over licensing, so the daily commodity leg uses Brent crude, which
is EIA data (US-government public domain, reliably hosted, cleanest possible
terms) and a liquid global-commodity barometer. The Phase 1 export basket (iron
ore, coal, gold, LNG from the World Bank) replaces this proxy.

Redistribution: FRED is free to use; individual series carry their source's
terms. EIA energy series are public domain. Confirm commercial-display terms for
the ICE BofA series before launch and attribute appropriately. None of these is
an ASX/S&P-licensed price product.
"""

from __future__ import annotations

import io
import time

import pandas as pd
import requests

FREDGRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

HY_OAS_SERIES_ID = "BAMLH0A0HYM2"
# Daily commodity series (EIA, public domain). Brent primary, WTI fallback.
BRENT_SERIES_ID = "DCOILBRENTEU"
WTI_SERIES_ID = "DCOILWTICO"

# Phase 1 monthly export-commodity basket: IMF Primary Commodity Prices, hosted
# on FRED (keyless), weighted toward Australia's principal export earners.
# (series id, leg name, basket weight). Weights are renormalised over whichever
# legs successfully load, so a single dead id degrades gracefully.
COMMODITY_BASKET = (
    ("PIORECRUSDM", "iron_ore", 0.35),
    ("PCOALAUUSDM", "coal_au", 0.20),
    ("PNGASJPUSDM", "lng_asia", 0.15),
    ("PALUMUSDM", "aluminium", 0.10),
    ("PCOPPUSDM", "copper", 0.10),
    ("PNICKUSDM", "nickel", 0.10),
)

_TIMEOUT = 60
_RETRIES = 4
_HEADERS = {"User-Agent": "asx-drivers-index/0.1"}


def _get_text(url: str, params: dict | None = None) -> str:
    """GET text with retries and backoff (FRED can be slow/throttled from CI)."""
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last = exc
            if attempt < _RETRIES - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
    raise last  # type: ignore[misc]


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith("<") or "<!doctype" in head or "<html" in head


def parse_fredgraph_csv(text: str, series_id: str | None = None) -> pd.Series:
    """Parse a FRED fredgraph CSV into a float Series indexed by date.

    The first column is the date (named DATE or observation_date depending on
    vintage); the value column is the series id. Missing observations are encoded
    as '.' and dropped.
    """
    if _looks_like_html(text):
        raise ValueError("FRED returned an HTML page, not CSV.")
    df = pd.read_csv(io.StringIO(text))
    cols = list(df.columns)
    if len(cols) < 2:
        raise ValueError(f"Unexpected FRED CSV columns: {cols}")
    date_col = cols[0]
    val_col = series_id if (series_id and series_id in cols) else cols[1]
    out = df[[date_col, val_col]].copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out[val_col] = pd.to_numeric(out[val_col], errors="coerce")  # '.' -> NaN
    s = out.dropna().set_index(date_col)[val_col].astype(float).sort_index()
    s.name = val_col
    return s


def load_series(series_id: str, text: str | None = None) -> pd.Series:
    """Load one FRED series by id (keyless). Pass ``text`` to parse offline."""
    if text is None:
        text = _get_text(FREDGRAPH_URL, params={"id": series_id})
    return parse_fredgraph_csv(text, series_id)


def load_hy_oas(text: str | None = None) -> pd.Series:
    """US high-yield credit spread (option-adjusted, percent)."""
    return load_series(HY_OAS_SERIES_ID, text).rename("hy_oas")


def load_commodity(text: str | None = None) -> pd.Series:
    """Daily commodity leg for Phase 0 (Brent crude, WTI fallback).

    A liquid daily global-commodity proxy; replaced by the Phase 1 export basket.
    Trying two EIA series guards against any single series id going dead.
    """
    if text is not None:
        return parse_fredgraph_csv(text).rename("commodity")
    errors = []
    for series_id in (BRENT_SERIES_ID, WTI_SERIES_ID):
        try:
            return load_series(series_id).rename("commodity")
        except Exception as exc:  # noqa: BLE001 - aggregate and report
            errors.append(f"{series_id}: {exc}")
    raise RuntimeError(
        "Could not load a commodity series from FRED -> " + " | ".join(errors)
    )


def build_commodity_basket(
    basket=COMMODITY_BASKET,
    texts: dict[str, str] | None = None,
) -> tuple[pd.Series, dict[str, float], list[str]]:
    """Build a weighted, monthly export-commodity basket index from FRED series.

    Each leg is rebased to 100 at the first common month, then combined with
    renormalised weights. Returns (basket_index, used_weights, errors). Legs that
    fail to load are skipped and their weight redistributed, so the basket still
    builds from the survivors. ``texts`` (series_id -> CSV) is for offline tests.
    """
    series: dict[str, pd.Series] = {}
    weights: dict[str, float] = {}
    errors: list[str] = []
    for series_id, name, weight in basket:
        try:
            text = texts.get(series_id) if texts else None
            if texts is not None and text is None:
                raise ValueError("no offline text supplied")
            series[name] = load_series(series_id, text)
            weights[name] = weight
        except Exception as exc:  # noqa: BLE001 - aggregate per leg
            errors.append(f"{series_id}: {exc}")
    if not series:
        raise RuntimeError(
            "Could not load any commodity basket leg from FRED -> " + " | ".join(errors)
        )
    df = pd.DataFrame(series).dropna()
    if df.empty:
        raise RuntimeError("Commodity basket legs do not overlap in time.")
    rebased = df / df.iloc[0] * 100.0
    wsum = sum(weights.values())
    basket_index = sum(rebased[name] * (weights[name] / wsum) for name in series)
    basket_index.name = "commodity_basket"
    return basket_index, {k: weights[k] / wsum for k in weights}, errors
