"""XJO (S&P/ASX 200) daily closes for Phase 0.

LICENSING NOTE (review point): the XJO index level is itself an S&P/ASX licensed
product, exactly like the A-VIX the spec is careful to avoid. For Phase 0 we use
a free source for internal validation only. Before any public display, resolve
this deliberately: either display only *derived* values (realised vol, momentum
%) and never the index level, or move the market proxy to the STW ETF / a
self-computed basket. Do not let the MVP's free XJO source quietly become the
production source.

Two free sources are supported, with 'auto' trying each in turn. Free finance
endpoints come and go (and several now front their data with anti-bot / JS
challenge walls), so the loader fails over and reports a clear, per-source error
rather than a cryptic parse failure. All parsers also accept text/JSON directly
so the pipeline can run offline from a local copy.
"""

from __future__ import annotations

import io

import pandas as pd
import requests

STOOQ_URL = "https://stooq.com/q/d/l/?s=^axjo&i=d"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EAXJO"

_TIMEOUT = 30
# A browser-like UA: some free endpoints (Yahoo especially) reject default
# library agents, and it makes anti-bot pages marginally less likely.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/json,text/plain,*/*",
}

SOURCES = ("stooq", "yahoo")


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith("<") or "<!doctype" in head or "<html" in head


def parse_stooq_csv(text: str) -> pd.Series:
    """Parse Stooq daily CSV (Date,Open,High,Low,Close,Volume) -> close Series."""
    if _looks_like_html(text):
        raise ValueError(
            "Stooq returned an HTML/anti-bot page, not CSV - the free Stooq "
            "endpoint is blocking automated requests. Try --xjo-source yahoo."
        )
    df = pd.read_csv(io.StringIO(text))
    if "Close" not in df.columns or "Date" not in df.columns:
        raise ValueError(f"Unexpected Stooq columns: {list(df.columns)}")
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date")["Close"].astype(float).sort_index().rename("xjo_close")


def _fetch_stooq() -> pd.Series:
    resp = requests.get(STOOQ_URL, timeout=_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    return parse_stooq_csv(resp.text)


def parse_yahoo_chart(payload: dict) -> pd.Series:
    """Parse Yahoo chart JSON -> close Series."""
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise ValueError(f"Yahoo chart error: {chart['error']}")
    results = chart.get("result")
    if not results:
        raise ValueError("Yahoo chart response had no result payload.")
    result = results[0]
    ts = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    idx = pd.to_datetime(ts, unit="s").normalize()
    s = pd.Series(closes, index=idx, name="xjo_close").astype(float)
    return s.dropna().sort_index()


def _fetch_yahoo(range_: str = "10y", interval: str = "1d") -> pd.Series:
    resp = requests.get(
        YAHOO_URL,
        params={"range": range_, "interval": interval},
        timeout=_TIMEOUT,
        headers=_HEADERS,
    )
    resp.raise_for_status()
    return parse_yahoo_chart(resp.json())


def load_xjo_close(source: str = "auto") -> pd.Series:
    """Fetch XJO daily closes from a free source.

    ``source``: 'stooq', 'yahoo', or 'auto' (try each in turn). For offline use,
    call the relevant ``parse_*`` helper directly with a local copy.
    """
    order = SOURCES if source == "auto" else (source,)
    fetchers = {"stooq": _fetch_stooq, "yahoo": _fetch_yahoo}
    errors = []
    for name in order:
        fetch = fetchers.get(name)
        if fetch is None:
            raise ValueError(f"Unknown source {name!r}; use 'stooq', 'yahoo' or 'auto'.")
        try:
            series = fetch()
            if series.empty:
                raise ValueError("returned an empty series")
            return series
        except Exception as exc:  # noqa: BLE001 - aggregate and report per source
            errors.append(f"{name}: {exc}")
    raise RuntimeError(
        "Could not load XJO closes from any source. Details -> " + " | ".join(errors)
    )
