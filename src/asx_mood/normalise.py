"""The shared normalisation engine (spec section 2).

Every component raw signal passes through the identical pipeline defined here:

    raw signal -> rolling z-score -> clip to [-3, 3] -> map to 0..100 -> (optional invert)

This is the spine of the index. Keeping it in one place is what guarantees that
"a volatility reading means different things in different regimes" - every signal
is always measured relative to its own recent normal, never an absolute threshold.
"""

from __future__ import annotations

import pandas as pd

# Spec defaults (section 2 / section 4).
NORMALISATION_WINDOW = 252  # trailing trading days (~1 year)
ZSCORE_CLIP = 3.0


def rolling_zscore(
    series: pd.Series,
    window: int = NORMALISATION_WINDOW,
    min_periods: int | None = None,
) -> pd.Series:
    """Z-score each point against the trailing ``window`` of its own history.

    The trailing window *includes* the current observation, matching the spec's
    "trailing mean and standard deviation of that raw signal". A point is left as
    NaN until at least ``min_periods`` observations are available, so the engine
    stays silent rather than emitting a meaningless score during warm-up.

    ``min_periods`` defaults to the full ``window``. For short Phase 0 series you
    can lower it, but publish whatever you choose (spec section 1).
    """
    if min_periods is None:
        min_periods = window
    roll = series.rolling(window=window, min_periods=min_periods)
    mean = roll.mean()
    std = roll.std(ddof=0)
    z = (series - mean) / std
    # A flat signal (std == 0) over a full window is "perfectly average", not a
    # warm-up gap: map it to z = 0. Genuine warm-up rows (mean is NaN) stay NaN.
    flat = mean.notna() & (std == 0.0)
    z = z.mask(flat, 0.0)
    return z


def zscore_to_score(z: pd.Series, clip: float = ZSCORE_CLIP) -> pd.Series:
    """Clip the z-score and map linearly to 0..100 (spec section 2, steps 4-5).

    z = 0  -> 50 (perfectly average)
    z = +clip -> 100
    z = -clip -> 0
    """
    z_clipped = z.clip(lower=-clip, upper=clip)
    return 50.0 + (z_clipped / clip) * 50.0


def normalise(
    raw: pd.Series,
    invert: bool = False,
    window: int = NORMALISATION_WINDOW,
    min_periods: int | None = None,
    clip: float = ZSCORE_CLIP,
) -> pd.Series:
    """Full per-component pipeline: raw signal -> 0..100 component score.

    Set ``invert=True`` for fear-positive signals (volatility), so a high raw
    value yields a low score (spec section 2, step 6).
    """
    z = rolling_zscore(raw, window=window, min_periods=min_periods)
    score = zscore_to_score(z, clip=clip)
    if invert:
        score = 100.0 - score
    return score
