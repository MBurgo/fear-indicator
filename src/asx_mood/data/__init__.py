"""Data loading and alignment for the ASX Mood Index.

Phase 0 sources (free, no API key):
  - XJO daily closes        -> data.xjo  (Stooq / Yahoo, or a local CSV)
  - AUD/USD daily            -> data.rba  (RBA F11.1)
  - 10y CGS bond yield       -> data.rba  (RBA F2)

All loaders return a tidy pandas Series indexed by a DatetimeIndex. ``align``
joins them onto a single trading-day calendar so the components can be computed
consistently across sources with different holiday calendars (review note).
"""

from __future__ import annotations

import pandas as pd


def align(
    frames: dict[str, pd.Series],
    how: str = "outer",
    ffill_limit: int | None = 3,
) -> pd.DataFrame:
    """Join named series onto one calendar and forward-fill small gaps.

    Sources have different holiday calendars (RBA vs equities); an outer join plus
    a short forward-fill prevents a one-source holiday from injecting a fake move,
    while ``ffill_limit`` stops a stale feed from being carried indefinitely.
    Rows where any column is still missing are dropped by the caller as needed.
    """
    df = pd.DataFrame(frames).sort_index()
    if ffill_limit is not None:
        df = df.ffill(limit=ffill_limit)
    return df
