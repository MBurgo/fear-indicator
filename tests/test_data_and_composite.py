import pandas as pd

from asx_mood import composite
from asx_mood.data import align
from asx_mood.data.rba import parse_rba_csv

# A miniature RBA-style CSV: metadata header block, then a "Series ID" row, then data.
SAMPLE_RBA = """Title,Exchange Rates
Description,Units of foreign currency per A$
Frequency,Daily
Series ID,FXRUSD,FXRTWI
03-Jan-2022,0.7200,60.1
04-Jan-2022,0.7185,60.0
05-Jan-2022,,59.8
06-Jan-2022,0.7150,59.5
"""


def test_parse_rba_picks_series_and_skips_blanks():
    s = parse_rba_csv(SAMPLE_RBA, "FXRUSD")
    assert list(s.values) == [0.72, 0.7185, 0.715]  # blank row dropped
    assert str(s.index[0].date()) == "2022-01-03"
    assert s.index.is_monotonic_increasing


def test_align_forward_fills_small_gaps():
    a = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2022-01-03", "2022-01-04", "2022-01-05"]))
    b = pd.Series([10.0, 30.0], index=pd.to_datetime(["2022-01-03", "2022-01-05"]))
    df = align({"a": a, "b": b}, ffill_limit=3)
    # b's holiday on the 4th is forward-filled from the 3rd, not left as a fake gap.
    assert df.loc["2022-01-04", "b"] == 10.0


def test_composite_requires_all_components_by_default():
    idx = pd.date_range("2022-01-01", periods=3)
    scores = pd.DataFrame(
        {"a": [50.0, 60.0, 70.0], "b": [40.0, None, 80.0]}, index=idx
    )
    comp = composite.composite(scores)
    assert pd.isna(comp.iloc[1])  # middle row missing a component
    assert comp.iloc[0] == 45.0


def test_calibrated_labels_span_the_extremes():
    # An averaged composite clusters near 50; percentile labels still reach extremes.
    idx = pd.date_range("2020-01-01", periods=500)
    series = pd.Series(50 + 4 * pd.Series(range(500)).sub(250).div(250).values, index=idx)
    labels = composite.label_calibrated(series)
    assert set(labels.dropna().unique()) >= {"Extreme Fear", "Neutral", "Extreme Greed"}


def test_calibrate_band_edges_ascending_within_history():
    import numpy as np

    s = pd.Series(np.linspace(30, 70, 500))
    edges = composite.calibrate_band_edges(s)
    assert edges == sorted(edges)
    assert 30 <= edges[0] and edges[-1] <= 70


def test_label_hysteresis_avoids_flicker():
    edges = [40, 45, 55, 60]
    idx = pd.date_range("2020-01-01", periods=6)
    series = pd.Series([54.0, 56.0, 54.0, 56.0, 54.0, 56.0], index=idx)
    labels = composite.label_series_with_edges(series, edges, composite.DRIVERS_LABELS, margin=2.0)
    # Oscillating <2 points across the 55 edge must not flip the label.
    assert labels.iloc[0] == "Neutral"
    assert labels.nunique() == 1


def test_label_changes_on_decisive_move():
    edges = [40, 45, 55, 60]
    idx = pd.date_range("2020-01-01", periods=3)
    series = pd.Series([50.0, 58.0, 65.0], index=idx)
    labels = composite.label_series_with_edges(series, edges, composite.DRIVERS_LABELS, margin=1.0)
    assert labels.iloc[0] == "Neutral"
    assert labels.iloc[-1] == "Strong Tailwind"
