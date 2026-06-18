import numpy as np
import pandas as pd

from asx_drivers import components, index
from asx_drivers.data.fred import parse_fredgraph_csv


def _series(values, start="2022-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=idx, dtype="float64")


def test_curve_slope_is_difference():
    y10 = _series([4.0, 4.1, 4.2])
    y2 = _series([3.0, 3.5, 4.3])
    slope = components.curve_slope_raw(y10, y2)
    assert list(slope.round(2)) == [1.0, 0.6, -0.1]  # last point inverted


def test_commodity_momentum_matches_pct_change():
    g = _series(np.linspace(1800, 1980, 100))
    m = components.commodity_momentum_raw(g, window=63)
    expected = (g.iloc[-1] - g.iloc[-64]) / g.iloc[-64]
    assert abs(m.iloc[-1] - expected) < 1e-12


def test_credit_risk_inverts_in_composite():
    # Rising credit spreads must lower the credit component score (headwind).
    rng = np.random.default_rng(3)
    n = 320
    audusd = _series(0.72 + np.cumsum(rng.normal(0, 0.001, n)))
    cgs10 = _series(np.full(n, 4.0) + rng.normal(0, 0.01, n))
    cgs2 = _series(np.full(n, 3.2) + rng.normal(0, 0.01, n))
    hy = _series(np.linspace(3.0, 8.0, n))  # steadily widening = fear
    months = pd.date_range("2021-01-01", periods=40, freq="MS")
    basket = pd.Series(np.linspace(100, 120, 40), index=months, name="commodity_basket")
    scores, _ = index.build(audusd, cgs10, cgs2, hy, basket, window=252)
    # With spreads at their widest vs the trailing year, the (inverted) credit
    # score should sit in the lower (headwind) half.
    assert scores["credit_risk"].iloc[-1] < 50


def test_parse_fredgraph_handles_missing_and_date_col_names():
    csv_a = "DATE,BAMLH0A0HYM2\n2024-01-02,3.50\n2024-01-03,.\n2024-01-04,3.60\n"
    s = parse_fredgraph_csv(csv_a, "BAMLH0A0HYM2")
    assert list(s.round(2)) == [3.50, 3.60]  # '.' row dropped
    # Newer vintage uses observation_date and an unknown value column name.
    csv_b = "observation_date,VALUE\n2024-01-02,1900.0\n2024-01-03,1910.5\n"
    s2 = parse_fredgraph_csv(csv_b)
    assert list(s2) == [1900.0, 1910.5]
    assert str(s2.index[0].date()) == "2024-01-02"
