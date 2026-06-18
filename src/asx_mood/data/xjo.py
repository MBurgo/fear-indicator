"""XJO (S&P/ASX 200) daily closes for Phase 0.

LICENSING NOTE (review point): the XJO index level is itself an S&P/ASX licensed
product, exactly like the A-VIX the spec is careful to avoid. For Phase 0 we use
a free source for internal validation only. Before any public display, resolve
this deliberately: either display only *derived* values (realised vol, momentum
%) and never the index level, or move the market proxy to the STW ETF / a
self-computed basket. Do not let the MVP's free XJO source quietly become the
production source.

Sourcing options, in order of reliability:
  - a LOCAL CSV you downloaded in a browser (--xjo-csv) - most reliable, since
    the browser clears the JS / cookie / rate-limit checks that block scripts;
  - Yahoo's chart API (rate-limited, rotates hosts and retries on 429);
  - Stooq's CSV endpoint (now fronted by a JavaScript anti-bot wall, usually
    fails for automated requests).
The CSV parser is tolerant of both Yahoo and Stooq download formats.
"""

from __future__ import annotations

import io
import time

import pandas as pd
import requests

STOOQ_URL = "https://stooq.com/q/d/l/?s=^axjo&i=d"
YAHOO_HOSTS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/%5EAXJO",
    "https://query2.finance.yahoo.com/v8/finance/chart/%5EAXJO",
)

_TIMEOUT = 30
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


def read_price_csv(text: str) -> pd.Series:
    """Parse a daily price CSV into a close Series (tolerant of Yahoo & Stooq).

    Accepts any CSV with a Date column and a Close (or Adj Close) column, which
    covers both the Yahoo download (Date,Open,High,Low,Close,Adj Close,Volume)
    and the Stooq download (Date,Open,High,Low,Close,Volume).
    """
    if _looks_like_html(text):
        raise ValueError("Got an HTML page, not CSV (likely an anti-bot wall).")
    df = pd.read_csv(io.StringIO(text))
    cols = {c.strip().lower(): c for c in df.columns}
    date_col = cols.get("date")
    close_col = cols.get("close") or cols.get("adj close") or cols.get("adjclose")
    if date_col is None or close_col is None:
        raise ValueError(
            f"CSV needs Date and Close columns; got {list(df.columns)}"
        )
    s = df[[date_col, close_col]].copy()
    s[date_col] = pd.to_datetime(s[date_col], errors="coerce")
    s[close_col] = pd.to_numeric(s[close_col], errors="coerce")
    s = s.dropna().set_index(date_col)[close_col].astype(float).sort_index()
    s.name = "xjo_close"
    return s


# Back-compat alias (older callers/tests import parse_stooq_csv).
parse_stooq_csv = read_price_csv


def load_xjo_from_csv(path: str) -> pd.Series:
    """Load XJO closes from a local CSV file downloaded via a browser."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        return read_price_csv(fh.read())


def _fetch_stooq() -> pd.Series:
    resp = requests.get(STOOQ_URL, timeout=_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    return read_price_csv(resp.text)


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


def _fetch_yahoo(range_: str = "10y", interval: str = "1d", attempts: int = 2) -> pd.Series:
    """Fetch from Yahoo, rotating hosts and backing off on 429 rate limits."""
    last = "no attempt made"
    for host in YAHOO_HOSTS:
        for k in range(attempts):
            try:
                resp = requests.get(
                    host,
                    params={"range": range_, "interval": interval},
                    timeout=_TIMEOUT,
                    headers=_HEADERS,
                )
                if resp.status_code == 429:
                    last = f"429 Too Many Requests from {host}"
                    time.sleep(2 * (k + 1))
                    continue
                resp.raise_for_status()
                return parse_yahoo_chart(resp.json())
            except requests.RequestException as exc:
                last = str(exc)
                break  # network/HTTP error other than 429: try next host
    raise ValueError(last)


def load_xjo_close(source: str = "auto") -> pd.Series:
    """Fetch XJO daily closes from a free source.

    ``source``: 'stooq', 'yahoo', or 'auto' (try each in turn). For the most
    reliable path use ``load_xjo_from_csv`` with a browser-downloaded file.
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
        "Could not load XJO closes from any network source. Details -> "
        + " | ".join(errors)
        + "  (Tip: download a daily CSV for ^AXJO in your browser and pass "
        "--xjo-csv PATH.)"
    )
