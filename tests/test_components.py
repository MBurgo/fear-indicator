import numpy as np
import pandas as pd

from asx_mood import components


def _series(values):
    idx = pd.bdate_range("2022-01-01", periods=len(values))
    return pd.Series(values, index=idx, dtype="float64")


def test_momentum_sign():
    # Rising series ends above its trailing MA -> positive momentum.
    s = _series(np.linspace(100, 200, 200))
    m = components.momentum_raw(s, window=125)
    assert m.iloc[-1] > 0


def test_realised_vol_positive_and_scales():
    rng = np.random.default_rng(2)
    calm = _series(100 * np.exp(np.cumsum(rng.normal(0, 0.002, 300))))
    wild = _series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300))))
    v_calm = components.realised_vol_raw(calm, window=20).iloc[-1]
    v_wild = components.realised_vol_raw(wild, window=20).iloc[-1]
    assert v_calm > 0 and v_wild > v_calm


def test_aud_momentum_matches_pct_change():
    s = _series(np.linspace(0.70, 0.77, 100))
    a = components.aud_momentum_raw(s, window=20)
    expected = (s.iloc[-1] - s.iloc[-21]) / s.iloc[-21]
    assert abs(a.iloc[-1] - expected) < 1e-12


def test_safe_haven_equity_outperformance_is_positive():
    # Equities up strongly, yields ~flat -> equities outperform bonds -> positive.
    eq = _series(np.linspace(100, 130, 60))
    yld = _series([4.0] * 60)
    sh = components.safe_haven_raw(eq, yld, horizon=20)
    assert sh.iloc[-1] > 0


def test_bond_return_rises_when_yields_fall():
    # Falling yields -> positive bond price return (duration effect).
    falling = _series(np.linspace(4.5, 3.5, 60))
    r = components.bond_total_return(falling, horizon=20, modified_duration=8.0)
    assert r.iloc[-1] > 0


def test_mcclellan_oscillator_is_stationary_vs_summation():
    # Persistent positive net advancing volume: a raw cumulative summation grows
    # without bound (non-stationary), but the oscillator settles to a stable level.
    idx = pd.bdate_range("2022-01-01", periods=400)
    adv = pd.Series(1_000_000.0, index=idx)
    dec = pd.Series(600_000.0, index=idx)
    osc = components.mcclellan_oscillator(adv, dec)
    summation = (adv - dec).cumsum()
    # Oscillator second-half variation is tiny relative to the summation's drift.
    assert osc.iloc[200:].std() < summation.iloc[200:].std()
