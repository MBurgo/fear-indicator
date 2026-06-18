"""Native-frequency normalisation and as-of daily assembly (spec section 5).

The index refreshes daily, but some components are monthly (the commodity basket)
or daily-but-lagged (ASIC short positioning). The rule that keeps this honest:

    normalise each component at its NATIVE frequency, then forward-fill the
    resulting 0-100 score onto the daily grid, stamped by the date the data was
    actually available (publication lag), never the reference date.

This module provides the three operations that implement that rule.
"""

from __future__ import annotations

import pandas as pd

from asx_mood.normalise import normalise


def daily_score(
    raw: pd.Series,
    invert: bool = False,
    window: int = 252,
    min_periods: int | None = None,
) -> pd.Series:
    """Normalise a daily raw signal to a 0..100 daily score (252-day window)."""
    return normalise(raw, invert=invert, window=window, min_periods=min_periods)


def monthly_score_to_daily(
    raw_monthly: pd.Series,
    daily_index: pd.DatetimeIndex,
    invert: bool = False,
    window: int = 36,
    min_periods: int | None = None,
    publication_lag_days: int = 45,
) -> pd.Series:
    """Normalise a monthly raw signal against a MONTHLY window, then forward-fill.

    A 252-trading-day window would hold only ~12 monthly observations and
    forward-filling would understate the standard deviation (repeated values), so
    the z-score is computed against ``window`` *monthly* observations and only
    then mapped to daily. ``publication_lag_days`` shifts each monthly value to
    roughly when it was actually released (IMF/World Bank monthly prices for month
    M appear in the middle of M+1), preventing look-ahead.
    """
    score_m = normalise(raw_monthly, invert=invert, window=window, min_periods=min_periods)
    score_m = score_m.dropna()
    if score_m.empty:
        return pd.Series(index=daily_index, dtype="float64")
    shifted = score_m.copy()
    shifted.index = shifted.index + pd.Timedelta(days=publication_lag_days)
    shifted = shifted.sort_index()
    # Drop any duplicate timestamps the shift may create, keeping the latest.
    shifted = shifted[~shifted.index.duplicated(keep="last")]
    return shifted.reindex(daily_index, method="ffill")


def lag_to_daily(
    score: pd.Series,
    daily_index: pd.DatetimeIndex,
    lag_bdays: int = 0,
) -> pd.Series:
    """Shift a (native-daily) score by ``lag_bdays`` business days, then ffill.

    Used for data that is daily but published with a delay (ASIC short positions
    are released T+4), so a reading dated D only becomes available at D+4.
    """
    s = score.dropna()
    if s.empty:
        return pd.Series(index=daily_index, dtype="float64")
    if lag_bdays > 0:
        s = s.copy()
        s.index = s.index + pd.tseries.offsets.BusinessDay(lag_bdays)
        s = s.sort_index()
        s = s[~s.index.duplicated(keep="last")]
    return s.reindex(daily_index, method="ffill")
