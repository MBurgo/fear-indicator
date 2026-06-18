import numpy as np
import pandas as pd

from asx_drivers import fetch_asic, frequency, index
from asx_drivers.data import asic, fred, synthetic


def test_asic_url_templates_format_with_date():
    urls = fetch_asic.urls_for(pd.Timestamp("2024-06-10"))
    assert any("RR20240610-001-SSDailyAggShortPos.csv" in u for u in urls)
    assert any("/2024/06/" in u for u in urls)  # year/month pattern present


def test_monthly_score_forward_fills_onto_daily_grid():
    months = pd.date_range("2018-01-01", periods=60, freq="MS")
    raw = pd.Series(np.linspace(0.0, 1.0, 60), index=months)  # trending up
    daily = pd.bdate_range("2018-01-01", periods=1000)
    out = frequency.monthly_score_to_daily(raw, daily, window=36, publication_lag_days=45)
    assert out.index.equals(daily)
    # After warm-up the daily series is populated and piecewise-constant between
    # monthly releases (forward-filled), not interpolated.
    tail = out.dropna()
    assert not tail.empty
    # Far more repeated values than unique ones => it is held, not interpolated.
    assert tail.nunique() < len(tail) / 10


def test_publication_lag_prevents_lookahead():
    months = pd.date_range("2020-01-01", periods=48, freq="MS")
    raw = pd.Series(np.arange(48.0), index=months)
    daily = pd.bdate_range("2020-01-01", periods=900)
    out = frequency.monthly_score_to_daily(raw, daily, window=12, publication_lag_days=45)
    # The score for a month must not be visible until ~45 days after month start.
    first_valid = out.first_valid_index()
    # 12-month warm-up ends at 2020-12-01; +45d publication lag lands in mid-Jan.
    assert first_valid >= pd.Timestamp("2021-01-10")


def test_lag_to_daily_shifts_business_days():
    idx = pd.bdate_range("2022-01-03", periods=10)
    score = pd.Series(range(10), index=idx, dtype="float64")
    daily = pd.bdate_range("2022-01-03", periods=20)
    out = frequency.lag_to_daily(score, daily, lag_bdays=4)
    # The value reported on day 0 only becomes available 4 business days later.
    assert pd.isna(out.iloc[0])
    assert out.loc[idx[0] + pd.tseries.offsets.BusinessDay(4)] == 0.0


def test_build_commodity_basket_offline_renormalises_weights():
    # Two legs supplied offline; weights should renormalise to sum to 1.
    texts = {
        "PIORECRUSDM": "DATE,PIORECRUSDM\n2020-01-01,100\n2020-02-01,110\n2020-03-01,120\n",
        "PCOALAUUSDM": "DATE,PCOALAUUSDM\n2020-01-01,50\n2020-02-01,52\n2020-03-01,55\n",
    }
    basket, weights, errors = fred.build_commodity_basket(texts=texts)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert set(weights) == {"iron_ore", "coal_au"}
    assert basket.iloc[0] == 100.0  # rebased to 100 at first month
    assert basket.is_monotonic_increasing  # both legs rose


def test_asic_parse_and_aggregate():
    text = (
        "Product\tProduct Code\tReported Short Positions\tTotal Product in Issue\t"
        "% of Total Product in Issue Reported as Short Positions\n"
        "BHP GROUP\tBHP\t1000000\t5000000000\t0.02\n"
        "COMMONWEALTH BANK\tCBA\t500000\t1700000000\t0.0294\n"
    )
    df = asic.parse_aggregate_file(text)
    assert list(df["code"]) == ["BHP", "CBA"]
    pct = asic.market_short_pct(df)
    expected = 100.0 * (1_000_000 + 500_000) / (5_000_000_000 + 1_700_000_000)
    assert abs(pct - expected) < 1e-9


def test_phase1_build_with_short_adds_component():
    inputs = synthetic.make_inputs(n_days=1500, seed=4)
    from asx_drivers.data import align

    daily = align(
        {k: inputs[k] for k in ["audusd", "cgs_10y_yield", "cgs_2y_yield", "hy_oas"]}
    ).dropna()
    scores, idx = index.build(
        daily["audusd"],
        daily["cgs_10y_yield"],
        daily["cgs_2y_yield"],
        daily["hy_oas"],
        inputs["commodity_basket"],
        short_pct=inputs["short_pct"],
    )
    assert list(scores.columns) == [
        "commodity",
        "aud",
        "curve_slope",
        "credit_risk",
        "short_positioning",
    ]
    assert idx.dropna().between(0, 100).all()
