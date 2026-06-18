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

import pandas as pd
import requests

FREDGRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

HY_OAS_SERIES_ID = "BAMLH0A0HYM2"
# Daily commodity series (EIA, public domain). Brent primary, WTI fallback.
BRENT_SERIES_ID = "DCOILBRENTEU"
WTI_SERIES_ID = "DCOILWTICO"

_TIMEOUT = 30
_HEADERS = {"User-Agent": "asx-drivers-index/0.1"}


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
        resp = requests.get(
            FREDGRAPH_URL, params={"id": series_id}, timeout=_TIMEOUT, headers=_HEADERS
        )
        resp.raise_for_status()
        text = resp.text
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
