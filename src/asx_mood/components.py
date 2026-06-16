"""Raw-signal calculations for each component (spec section 3).

Each function returns the *raw* signal as a pandas Series indexed by date. The
raw signal is then handed to ``normalise.normalise`` to become a 0..100 score.
Phase 0 covers the four free, no-key components; the two breadth components
(strength, breadth) arrive in Phase 1 with the EODHD universe feed.

All inputs are assumed to be aligned to a common trading-day DatetimeIndex by the
caller (see data.align). These functions do not fetch or align.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Phase 0 components
# ---------------------------------------------------------------------------


def momentum_raw(xjo_close: pd.Series, window: int = 125) -> pd.Series:
    """XJO level relative to its own simple moving average (spec 3.1).

    momentum_raw = (close - SMA_window) / SMA_window      (high = greed)
    """
    sma = xjo_close.rolling(window=window, min_periods=window).mean()
    return (xjo_close - sma) / sma


def realised_vol_raw(xjo_close: pd.Series, window: int = 20) -> pd.Series:
    """Annualised realised volatility of XJO daily log returns (spec 3.5).

    high = fear, so the component score is inverted downstream.
    """
    log_ret = np.log(xjo_close / xjo_close.shift(1))
    rolling_std = log_ret.rolling(window=window, min_periods=window).std(ddof=0)
    return rolling_std * np.sqrt(252.0)


def aud_momentum_raw(audusd: pd.Series, window: int = 20) -> pd.Series:
    """20-day momentum of AUD/USD (spec 3.6).

    aud_raw = (AUD_today - AUD_{t-window}) / AUD_{t-window}   (high = greed)
    """
    return audusd.pct_change(periods=window)


def bond_total_return(
    yield_pct: pd.Series,
    horizon: int = 20,
    modified_duration: float = 8.0,
) -> pd.Series:
    """Approximate total return of a 10y CGS proxy over ``horizon`` days (spec 3.4).

    The RBA F2 series is a *yield* on a notional constant-maturity 10y bond, not a
    tradeable price, so we synthesise a price+carry return:

        total_return ~= carry - modified_duration * change_in_yield

    where yields are in percent. Carry is the yield earned over the horizon; the
    price leg is the first-order duration approximation. ``modified_duration`` is
    a stated assumption (~8-8.5 for a 10y CGS) and should be published.
    """
    y = yield_pct / 100.0  # to decimal
    delta_y = y - y.shift(horizon)
    carry = y.shift(horizon) * (horizon / 252.0)
    price_return = -modified_duration * delta_y
    return carry + price_return


def safe_haven_raw(
    xjo_close: pd.Series,
    bond_yield_pct: pd.Series,
    horizon: int = 20,
    modified_duration: float = 8.0,
) -> pd.Series:
    """Equity return minus bond return over ``horizon`` days (spec 3.4).

    safe_haven_raw = ret_h(equities) - ret_h(bonds)          (high = greed)

    Equities outperforming bonds signals risk appetite; bonds outperforming
    signals a flight to safety (fear).
    """
    equity_ret = xjo_close.pct_change(periods=horizon)
    bond_ret = bond_total_return(
        bond_yield_pct, horizon=horizon, modified_duration=modified_duration
    )
    return equity_ret - bond_ret


# ---------------------------------------------------------------------------
# Phase 1 breadth components (review fix: McClellan oscillator, not raw summation)
# ---------------------------------------------------------------------------


def strength_raw(
    new_highs: pd.Series,
    new_lows: pd.Series,
    total_issues: pd.Series,
) -> pd.Series:
    """Net 52-week highs minus lows as a share of issues (spec 3.2). Phase 1.

    strength_raw = (new_52wk_highs - new_52wk_lows) / total_issues   (high = greed)
    """
    return (new_highs - new_lows) / total_issues


def mcclellan_oscillator(
    adv_volume: pd.Series,
    dec_volume: pd.Series,
    fast: int = 19,
    slow: int = 39,
) -> pd.Series:
    """Volume-weighted breadth as a McClellan Oscillator (spec 3.3, review-fixed). Phase 1.

    Review note: the spec's raw running *summation* is a cumulative sum, i.e. a
    non-stationary I(1) series whose rolling mean/std drift with the trend, making
    a 252-day z-score ill-defined. The McClellan Oscillator (difference of fast and
    slow EMAs of net advancing volume) is stationary and mean-reverting, so it
    z-scores cleanly. high = greed.
    """
    net = adv_volume - dec_volume
    ema_fast = net.ewm(span=fast, adjust=False).mean()
    ema_slow = net.ewm(span=slow, adjust=False).mean()
    return ema_fast - ema_slow
