import numpy as np
import pandas as pd

from asx_mood.normalise import normalise, rolling_zscore, zscore_to_score


def test_zscore_to_score_anchors():
    z = pd.Series([-3.0, 0.0, 3.0])
    s = zscore_to_score(z)
    assert s.tolist() == [0.0, 50.0, 100.0]


def test_zscore_to_score_clips_beyond_band():
    z = pd.Series([-10.0, 10.0])
    s = zscore_to_score(z)
    assert s.tolist() == [0.0, 100.0]


def test_rolling_zscore_matches_manual():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=300))
    z = rolling_zscore(x, window=252, min_periods=252)
    # Last point: manual z against trailing 252 incl. current.
    win = x.iloc[-252:]
    expected = (x.iloc[-1] - win.mean()) / win.std(ddof=0)
    assert abs(z.iloc[-1] - expected) < 1e-9


def test_warmup_is_nan_until_min_periods():
    x = pd.Series(np.arange(100, dtype=float))
    z = rolling_zscore(x, window=50, min_periods=50)
    assert z.iloc[:49].isna().all()
    assert not np.isnan(z.iloc[49])


def test_flat_signal_maps_to_neutral_not_nan():
    x = pd.Series([5.0] * 60)
    z = rolling_zscore(x, window=50, min_periods=50)
    # Once the window is full, a flat signal is "perfectly average" -> z 0 -> 50.
    assert z.iloc[-1] == 0.0
    assert zscore_to_score(z).iloc[-1] == 50.0


def test_invert_flips_fear_positive_signal():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(size=300))
    base = normalise(x, invert=False, window=252, min_periods=252)
    inv = normalise(x, invert=True, window=252, min_periods=252)
    assert abs((base.iloc[-1] + inv.iloc[-1]) - 100.0) < 1e-9
