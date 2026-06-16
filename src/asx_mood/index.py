"""Phase 0 orchestration: inputs -> component scores -> composite -> reading.

This wires the four free components through the shared normalisation engine and
the compositor. Phase 1 adds the two breadth components by extending
``COMPONENT_SPECS`` and supplying the EODHD universe inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import components, composite
from .normalise import normalise


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    invert: bool  # True for fear-positive signals (volatility)


# Phase 0 component set (order = display order).
PHASE0_COMPONENTS = [
    ComponentSpec("momentum", invert=False),
    ComponentSpec("strength_placeholder", invert=False),  # off in Phase 0
    ComponentSpec("safe_haven", invert=False),
    ComponentSpec("volatility", invert=True),
    ComponentSpec("aud", invert=False),
]

# Active in Phase 0 (the four free, no-key components).
PHASE0_ACTIVE = ["momentum", "safe_haven", "volatility", "aud"]


def raw_signals(
    xjo_close: pd.Series,
    audusd: pd.Series,
    cgs_10y_yield: pd.Series,
    modified_duration: float = 8.0,
) -> pd.DataFrame:
    """Compute the four Phase 0 raw signals on an aligned index."""
    return pd.DataFrame(
        {
            "momentum": components.momentum_raw(xjo_close),
            "safe_haven": components.safe_haven_raw(
                xjo_close, cgs_10y_yield, modified_duration=modified_duration
            ),
            "volatility": components.realised_vol_raw(xjo_close),
            "aud": components.aud_momentum_raw(audusd),
        }
    )


def component_scores(
    raws: pd.DataFrame,
    window: int = 252,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Normalise each raw signal to a 0..100 score, inverting where fear-positive."""
    invert = {"volatility": True}
    out = {}
    for col in raws.columns:
        out[col] = normalise(
            raws[col],
            invert=invert.get(col, False),
            window=window,
            min_periods=min_periods,
        )
    return pd.DataFrame(out)


def build(
    xjo_close: pd.Series,
    audusd: pd.Series,
    cgs_10y_yield: pd.Series,
    window: int = 252,
    min_periods: int | None = None,
    modified_duration: float = 8.0,
) -> tuple[pd.DataFrame, pd.Series]:
    """End-to-end Phase 0: -> (component_scores, composite_index).

    Inputs must already be aligned to a common calendar (see data.align).
    """
    raws = raw_signals(
        xjo_close, audusd, cgs_10y_yield, modified_duration=modified_duration
    )
    scores = component_scores(raws, window=window, min_periods=min_periods)
    idx = composite.composite(scores)
    return scores, idx
