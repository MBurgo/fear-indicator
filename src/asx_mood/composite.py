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

# Quantiles used to calibrate fixed band EDGES from the index's own history.
CALIBRATION_QUANTILES = (0.10, 0.30, 0.70, 0.90)
# Five label sets sharing the same edges; pick per product.
MOOD_LABELS = ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"]
DRIVERS_LABELS = ["Strong Headwind", "Headwind", "Neutral", "Tailwind", "Strong Tailwind"]


def calibrate_band_edges(
    series: pd.Series, quantiles: tuple[float, ...] = CALIBRATION_QUANTILES
) -> list[float]:
    """Calibrate four ascending score thresholds from the index's own history.

    Unlike rank-against-all-history labelling, these edges are computed ONCE and
    then applied as fixed score cutoffs, so "score X = label Y" is a stable,
    publishable mapping and a past day's label never changes retroactively. Still
    distribution-aware, so it preserves the band-compression fix. Falls back to
    the spec's fixed edges when there is too little history to calibrate.
    """
    s = series.dropna()
    if len(s) < 60:
        return [25.0, 45.0, 55.0, 75.0]
    edges = [round(float(s.quantile(q)), 1) for q in quantiles]
    # Guard against ties producing non-ascending edges.
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = edges[i - 1] + 0.1
    return edges


def _band_index(value: float, edges: list[float]) -> int:
    return sum(value >= e for e in edges)


def label_with_edges(score: float, edges: list[float], names: list[str]) -> str:
    """Label a single score using fixed band edges."""
    return names[_band_index(score, edges)]


def label_series_with_edges(
    series: pd.Series,
    edges: list[float],
    names: list[str],
    margin: float = 1.0,
) -> pd.Series:
    """Label a series with fixed edges plus hysteresis to avoid boundary flicker.

    The label only changes once the score moves ``margin`` points *past* the band
    boundary it is leaving, so a value hovering on a cutoff does not flip the
    label day to day.
    """
    labels = pd.Series(index=series.index, dtype="object")
    current: int | None = None
    for ts, value in series.items():
        if pd.isna(value):
            labels[ts] = None
            continue
        idx = _band_index(value, edges)
        if current is None:
            current = idx
        elif idx > current and value >= edges[current] + margin:
            current = idx
        elif idx < current and value < edges[current - 1] - margin:
            current = idx
        labels[ts] = names[current]
    return labels


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
    scores: pd.DataFrame,
    index: pd.Series,
    calibrate: bool = True,
    edges: list[float] | None = None,
    names: list[str] | None = None,
    margin: float = 1.0,
) -> Reading:
    """Build the most recent valid Reading from component scores and composite.

    If ``edges`` and ``names`` are given, labels use stable calibrated edges with
    hysteresis (preferred for display). Otherwise falls back to ``calibrate``
    (rank-based) or fixed bands.
    """
    valid = index.dropna()
    if valid.empty:
        raise ValueError("No valid composite values - not enough history yet.")
    date = valid.index[-1]
    score = float(valid.iloc[-1])
    if edges is not None and names is not None:
        label = str(label_series_with_edges(index, edges, names, margin).loc[date])
    elif calibrate:
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
