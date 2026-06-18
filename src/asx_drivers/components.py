"""Raw-signal calculations for the ASX Drivers Index (spec section 3).

Phase 0 covers the four fully-daily components. Each returns a raw signal Series
to be normalised by the shared ``asx_mood.normalise`` engine. Inputs are assumed
aligned to a common trading-day index by the caller (see asx_drivers.data.align).
"""

from __future__ import annotations

import pandas as pd

# Reuse the AUD momentum calculation from the Mood Index - identical definition.
from asx_mood.components import aud_momentum_raw  # noqa: F401  (re-exported)


def commodity_momentum_raw(price: pd.Series, window: int = 63) -> pd.Series:
    """Momentum of a commodity (Phase 0: gold) over ``window`` days (spec 3.1).

    63 trading days ~= 3 months. High = tailwind (greed). In Phase 1 ``price`` is
    the weighted export basket; in Phase 0 it is the daily gold leg.
    """
    return price.pct_change(periods=window)


def curve_slope_raw(yield_10y: pd.Series, yield_2y: pd.Series) -> pd.Series:
    """Government yield-curve slope, 10y minus 2y (spec 3.3).

    slope_raw = yield_10y - yield_2y  (percentage points). High/steeper =
    tailwind; inversion = recession warning = headwind.
    """
    return yield_10y - yield_2y


def credit_spread_raw(hy_oas: pd.Series) -> pd.Series:
    """US high-yield credit spread level (spec 3.4).

    High/widening spreads = global risk-off = headwind, so the component score is
    inverted downstream. Returns the level (z-scored against its own recent
    history, like the volatility component in the Mood Index).
    """
    return hy_oas
