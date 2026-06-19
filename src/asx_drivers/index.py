"""Phase 1 orchestration for the ASX Drivers Index.

Assembles five components onto a daily grid using native-frequency normalisation
and as-of forward-fill (spec section 5):

  daily   - AUD risk flow, yield-curve slope, global credit risk (inverted)
  monthly - export commodity basket (iron ore, coal, LNG, base metals)
  daily/T+4 - ASIC short positioning (inverted), optional

The short component is optional: if no ASIC data is supplied the index runs on
the other four. The composite requires every *active* component to be present, so
the headline reading always uses the full set (early history is trimmed during
warm-up).
"""

from __future__ import annotations

import pandas as pd

from asx_mood import composite

from . import components, frequency

DAILY_WINDOW = 252
MONTHLY_WINDOW = 36
COMMODITY_MOMENTUM_MONTHS = 3
SHORT_LAG_BDAYS = 4
# ASIC history is often shorter / patchier than the market series, so let the
# short component emit once it has ~200 observations (still a ~1-year window).
SHORT_MIN_PERIODS = 200

ORDER = [
    "commodity", "aud", "curve_slope", "bbsw_stress", "credit_risk",
    "volatility", "short_positioning",
]


def build(
    audusd: pd.Series,
    cgs_10y_yield: pd.Series,
    cgs_2y_yield: pd.Series,
    hy_oas: pd.Series,
    commodity_basket: pd.Series,
    short_pct: pd.Series | None = None,
    bbsw_spread: pd.Series | None = None,
    window: int = DAILY_WINDOW,
    monthly_window: int = MONTHLY_WINDOW,
    min_periods: int | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """End-to-end Phase 1: inputs -> (component_scores, composite_index).

    The daily inputs (audusd, yields, hy_oas) must already be aligned to a common
    daily index. ``commodity_basket`` is monthly; ``short_pct`` is daily (its own
    report dates) or None.
    """
    daily_index = audusd.index

    scores: dict[str, pd.Series] = {}

    # Monthly component: normalise against a monthly window, then as-of ffill.
    scores["commodity"] = frequency.monthly_score_to_daily(
        components.commodity_momentum_raw(commodity_basket, window=COMMODITY_MOMENTUM_MONTHS),
        daily_index,
        invert=False,
        window=monthly_window,
    )

    # Daily components.
    scores["aud"] = frequency.daily_score(
        components.aud_momentum_raw(audusd), window=window, min_periods=min_periods
    )
    scores["curve_slope"] = frequency.daily_score(
        components.curve_slope_raw(cgs_10y_yield, cgs_2y_yield),
        window=window,
        min_periods=min_periods,
    )

    # Optional bank funding-stress component (3m BBSW - cash rate): high spread =
    # stress = headwind, inverted. On its own RBA F1 calendar, so reindex + ffill.
    if bbsw_spread is not None and not bbsw_spread.dropna().empty:
        bbsw_score = frequency.daily_score(
            components.funding_stress_raw(bbsw_spread),
            invert=True,
            window=window,
            min_periods=min_periods,
        )
        scores["bbsw_stress"] = bbsw_score.reindex(daily_index, method="ffill")

    scores["credit_risk"] = frequency.daily_score(
        components.credit_spread_raw(hy_oas),
        invert=True,
        window=window,
        min_periods=min_periods,
    )

    # Realised volatility of the AUD as a fear/turbulence proxy: high vol = fear =
    # headwind, so inverted. Reuses the AUD series already pulled for the momentum
    # component (direction there; magnitude here).
    scores["volatility"] = frequency.daily_score(
        components.realised_vol_raw(audusd),
        invert=True,
        window=window,
        min_periods=min_periods,
    )

    # Optional daily-but-lagged component.
    if short_pct is not None and not short_pct.dropna().empty:
        short_score = frequency.daily_score(
            components.short_interest_raw(short_pct),
            invert=True,
            window=window,
            min_periods=min(window, SHORT_MIN_PERIODS),
        )
        scores["short_positioning"] = frequency.lag_to_daily(
            short_score, daily_index, lag_bdays=SHORT_LAG_BDAYS
        )

    active = [c for c in ORDER if c in scores]
    df_scores = pd.DataFrame({c: scores[c] for c in active}).reindex(daily_index)
    idx = composite.composite(df_scores)
    return df_scores, idx
