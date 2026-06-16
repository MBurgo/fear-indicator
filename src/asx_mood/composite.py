"""Compositing and display labelling (spec section 2).

Combines the per-component 0..100 scores into the headline index and assigns a
mood label. Includes the review fix for band compression: averaging several
components shrinks the composite's variance toward 50, so the naive 0-100 label
cutoffs would almost never reach the extremes. We therefore default to labelling
by the composite's own historical percentiles, while keeping the fixed cutoffs
available for comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Fixed display bands from the spec (section 2). Used when calibrate=False.
FIXED_BANDS = [
    (0, 24, "Extreme Fear"),
    (25, 44, "Fear"),
    (45, 55, "Neutral"),
    (56, 74, "Greed"),
    (75, 100, "Extreme Greed"),
]

# Percentile cutoffs for calibrated labels (review fix). Tune to taste.
PERCENTILE_BANDS = [
    (0.10, "Extreme Fear"),
    (0.30, "Fear"),
    (0.70, "Neutral"),
    (0.90, "Greed"),
    (1.01, "Extreme Greed"),  # 1.01 so the top percentile is inclusive
]


def composite(scores: pd.DataFrame, min_components: int | None = None) -> pd.Series:
    """Equal-weighted mean of the component scores, row by row (spec section 2).

    ``scores`` has one column per component, indexed by date. By default a row
    must have *every* component present to produce a value (``min_components`` =
    number of columns); lower it to tolerate a temporarily missing feed.
    """
    if min_components is None:
        min_components = scores.shape[1]
    present = scores.notna().sum(axis=1)
    mean = scores.mean(axis=1, skipna=True)
    return mean.where(present >= min_components)


def label_fixed(score: float) -> str:
    """Label a single composite score using the spec's fixed 0-100 bands."""
    for lo, hi, name in FIXED_BANDS:
        if lo <= score <= hi:
            return name
    return "Neutral"


def label_calibrated(series: pd.Series) -> pd.Series:
    """Label each point by where it falls in the composite's own distribution.

    This is the review fix: an averaged composite rarely reaches a raw 0-24 or
    75-100, so we rank against history instead. Requires enough history to be
    meaningful - publish the lookback you use.
    """
    ranks = series.rank(pct=True)
    labels = pd.Series(index=series.index, dtype="object")
    prev = 0.0
    for cutoff, name in PERCENTILE_BANDS:
        mask = (ranks > prev) & (ranks <= cutoff)
        labels[mask] = name
        prev = cutoff
    return labels


@dataclass
class Reading:
    """A single day's index reading, ready for display or JSON serialisation."""

    date: str
    score: int
    label: str
    components: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "score": self.score,
            "label": self.label,
            "components": {k: round(v, 1) for k, v in self.components.items()},
        }


def latest_reading(
    scores: pd.DataFrame, index: pd.Series, calibrate: bool = True
) -> Reading:
    """Build the most recent valid Reading from component scores and composite."""
    valid = index.dropna()
    if valid.empty:
        raise ValueError("No valid composite values - not enough history yet.")
    date = valid.index[-1]
    score = float(valid.iloc[-1])
    if calibrate:
        label = str(label_calibrated(index).loc[date])
    else:
        label = label_fixed(score)
    comps = {col: float(scores.loc[date, col]) for col in scores.columns}
    return Reading(
        date=date.strftime("%Y-%m-%d"),
        score=int(round(score)),
        label=label,
        components=comps,
    )
