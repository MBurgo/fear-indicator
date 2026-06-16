"""XJO (S&P/ASX 200) daily closes for Phase 0.

LICENSING NOTE (review point): the XJO index level is itself an S&P/ASX licensed
product, exactly like the A-VIX the spec is careful to avoid. For Phase 0 we use
a free source for internal validation only. Before any public display, resolve
this deliberately: either display only *derived* values (realised vol, momentum
%) and never the index level, or move the market proxy to the STW ETF / a
self-computed basket. Do not let the MVP's free XJO source quietly become the
production source.

Two free sources are supported; both can also be read from a local CSV so the
pipeline runs without network access.
"""

from __future__ import annotations

import io

import pandas as pd
import requests

STOOQ_URL = "https://stooq.com/q/d/l/?s=^axjo&i=d"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EAXJO"

_TIMEOUT = 30
_HEADERS = {"User-Agent": "asx-mood-index/0.1"}


def parse_stooq_csv(text: str) -> pd.Series:
    """Parse Stooq daily CSV (Date,Open,High,Low,Close,Volume) -> close Series."""
    df = pd.read_csv(io.StringIO(text))
    if "Close" not in df.columns or "Date" not in df.columns:
        raise ValueError(f"Unexpected Stooq columns: {list(df.columns)}")
    df["Date"] = pd.to_datetime(df["Date"])
    return (
        df.set_index("Date")["Close"].astype(float).sort_index().rename("xjo_close")
    )


def _fetch_stooq() -> pd.Series:
    resp = requests.get(STOOQ_URL, timeout=_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    return parse_stooq_csv(resp.text)


def parse_yahoo_chart(payload: dict) -> pd.Series:
    """Parse Yahoo chart JSON -> close Series (fallback source)."""
    result = payload["chart"]["result"][0]
    ts = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    idx = pd.to_datetime(ts, unit="s").normalize()
    s = pd.Series(closes, index=idx, name="xjo_close").astype(float)
    return s.dropna().sort_index()


def _fetch_yahoo(range_: str = "5y", interval: str = "1d") -> pd.Series:
    resp = requests.get(
        YAHOO_URL,
        params={"range": range_, "interval": interval},
        timeout=_TIMEOUT,
        headers=_HEADERS,
    )
    resp.raise_for_status()
    return parse_yahoo_chart(resp.json())


def load_xjo_close(source: str = "stooq") -> pd.Series:
    """Fetch XJO daily closes from a free source ('stooq' or 'yahoo').

    For offline / local-CSV use, parse with ``parse_stooq_csv`` directly instead.
    """
    if source == "stooq":
        return _fetch_stooq()
    if source == "yahoo":
        return _fetch_yahoo()
    raise ValueError(f"Unknown source {source!r}; use 'stooq' or 'yahoo'.")
