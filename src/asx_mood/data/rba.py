"""RBA statistical-table loaders (free, official, redistribution-clean).

RBA CSV tables carry a metadata header block (Title, Description, Frequency,
Type, Units, Source, Publication date, Series ID) followed by dated rows. The
column headers we key on live in the "Series ID" row, not the first row, so the
parser locates that row rather than assuming a fixed header position.

  F11.1 - exchange rates (daily). AUD/USD series id: FXRUSD
  F2    - capital market yields (daily). 10y CGS series id: FCMYGBAG10
"""

from __future__ import annotations

import io

import pandas as pd
import requests

F11_URL = "https://www.rba.gov.au/statistics/tables/csv/f11.1-data.csv"
F2_URL = "https://www.rba.gov.au/statistics/tables/csv/f2-data.csv"

AUDUSD_SERIES_ID = "FXRUSD"
CGS_10Y_SERIES_ID = "FCMYGBAG10"
CGS_2Y_SERIES_ID = "FCMYGBAG2"

_TIMEOUT = 30


def _fetch(url: str) -> str:
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "asx-mood-index/0.1"})
    resp.raise_for_status()
    return resp.text


def parse_rba_csv(text: str, series_id: str) -> pd.Series:
    """Extract one series, by Series ID, from RBA CSV text.

    Returns a float Series indexed by date, ascending, with missing values dropped.
    """
    rows = list(csv_rows(text))
    header_idx = next(
        (i for i, r in enumerate(rows) if r and r[0].strip() == "Series ID"), None
    )
    if header_idx is None:
        raise ValueError("Could not find 'Series ID' header row in RBA CSV")
    header = [c.strip() for c in rows[header_idx]]
    try:
        col = header.index(series_id)
    except ValueError as exc:
        raise ValueError(
            f"Series id {series_id!r} not in RBA table. Available: {header[1:]}"
        ) from exc

    dates, values = [], []
    for r in rows[header_idx + 1 :]:
        if not r or not r[0].strip():
            continue
        date = pd.to_datetime(r[0].strip(), dayfirst=True, errors="coerce")
        if pd.isna(date) or col >= len(r):
            continue
        raw = r[col].strip()
        if raw == "":
            continue
        try:
            values.append(float(raw))
            dates.append(date)
        except ValueError:
            continue
    return pd.Series(values, index=pd.DatetimeIndex(dates), name=series_id).sort_index()


def csv_rows(text: str):
    import csv

    yield from csv.reader(io.StringIO(text))


def load_audusd(text: str | None = None) -> pd.Series:
    """AUD/USD daily from RBA F11.1. Pass ``text`` to parse a local copy offline."""
    if text is None:
        text = _fetch(F11_URL)
    return parse_rba_csv(text, AUDUSD_SERIES_ID).rename("audusd")


def load_cgs_10y_yield(text: str | None = None) -> pd.Series:
    """10y Commonwealth Government bond yield (percent) from RBA F2."""
    if text is None:
        text = _fetch(F2_URL)
    return parse_rba_csv(text, CGS_10Y_SERIES_ID).rename("cgs_10y_yield")


def load_cgs_2y_yield(text: str | None = None) -> pd.Series:
    """2y Commonwealth Government bond yield (percent) from RBA F2."""
    if text is None:
        text = _fetch(F2_URL)
    return parse_rba_csv(text, CGS_2Y_SERIES_ID).rename("cgs_2y_yield")
