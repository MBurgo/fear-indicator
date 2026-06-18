"""Phase 0 orchestration for the ASX Drivers Index.

Wires the four fully-daily components through the shared normalisation engine and
compositor. Phase 1 adds the mixed-frequency commodity basket and the ASIC
short-positioning component (see docs/asx-drivers-spec.md section 5).
"""

from __future__ import annotations

import pandas as pd

from asx_mood import composite
from asx_mood.normalise import normalise

from . import components

# Active Phase 0 components, in display order. ``invert`` is True for
# headwind-positive signals (credit risk).
PHASE0_INVERT = {"credit_risk": True}
PHASE0_ORDER = ["commodity", "aud", "curve_slope", "credit_risk"]


def raw_signals(
    audusd: pd.Series,
    gold: pd.Series,
    cgs_10y_yield: pd.Series,
    cgs_2y_yield: pd.Series,
    hy_oas: pd.Series,
) -> pd.DataFrame:
    """Compute the four Phase 0 raw signals on an aligned index."""
    return pd.DataFrame(
        {
            "commodity": components.commodity_momentum_raw(gold),
            "aud": components.aud_momentum_raw(audusd),
            "curve_slope": components.curve_slope_raw(cgs_10y_yield, cgs_2y_yield),
            "credit_risk": components.credit_spread_raw(hy_oas),
        }
    )


def component_scores(
    raws: pd.DataFrame,
    window: int = 252,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Normalise each raw signal to 0..100, inverting headwind-positive signals."""
    out = {}
    for col in PHASE0_ORDER:
        out[col] = normalise(
            raws[col],
            invert=PHASE0_INVERT.get(col, False),
            window=window,
            min_periods=min_periods,
        )
    return pd.DataFrame(out)


def build(
    audusd: pd.Series,
    gold: pd.Series,
    cgs_10y_yield: pd.Series,
    cgs_2y_yield: pd.Series,
    hy_oas: pd.Series,
    window: int = 252,
    min_periods: int | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """End-to-end Phase 0: aligned inputs -> (component_scores, composite_index)."""
    raws = raw_signals(audusd, gold, cgs_10y_yield, cgs_2y_yield, hy_oas)
    scores = component_scores(raws, window=window, min_periods=min_periods)
    idx = composite.composite(scores)
    return scores, idx
