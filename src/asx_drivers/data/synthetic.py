"""Synthetic Phase 1 inputs for the ASX Drivers Index (offline demo + tests).

Generates a coherent set of driver series around a shared latent risk factor:
daily AUD/USD, 2y & 10y CGS yields, US high-yield spread; a MONTHLY export
commodity basket; and a daily ASIC-style market short percentage. Includes one
risk-off episode so the gauge has something to react to. NOT a data source.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_inputs(
    n_days: int = 1800,
    seed: int = 11,
    start: str = "2019-01-01",
) -> dict[str, pd.Series]:
    """Return synthetic Phase 1 driver inputs (daily + monthly + short)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n_days)

    # Latent global risk factor: positive = risk-on, with one risk-off episode.
    risk = np.cumsum(rng.normal(0, 1, n_days) * 0.05)
    shock_lo = int(n_days * 0.62)
    risk[shock_lo : shock_lo + 25] -= np.linspace(0, 3.5, 25)
    d_risk = np.diff(np.concatenate([[risk[0]], risk]))

    # AUD/USD: rises with risk-on.
    aud_ret = 0.0006 * d_risk + rng.normal(0, 0.003, n_days)
    audusd = pd.Series(0.72 * np.exp(np.cumsum(aud_ret)), index=idx, name="audusd")

    # 10y / 2y CGS yields: fall in risk-off; 2y reacts more (curve flattens).
    y10 = np.empty(n_days); y10[0] = 4.0
    y2 = np.empty(n_days); y2[0] = 3.2
    for t in range(1, n_days):
        y10[t] = y10[t - 1] + 0.01 * (4.0 - y10[t - 1]) + 0.03 * d_risk[t] + rng.normal(0, 0.02)
        y2[t] = y2[t - 1] + 0.01 * (3.4 - y2[t - 1]) + 0.05 * d_risk[t] + rng.normal(0, 0.02)
    cgs_10y = pd.Series(y10, index=idx, name="cgs_10y_yield").clip(lower=0.25)
    cgs_2y = pd.Series(y2, index=idx, name="cgs_2y_yield").clip(lower=0.1)

    # US HY OAS (percent): low in risk-on, spikes in risk-off.
    hy = 3.5 - 0.25 * risk
    hy[shock_lo : shock_lo + 30] += np.linspace(0, 4.0, 30)
    hy_oas = pd.Series(hy, index=idx, name="hy_oas").clip(lower=2.0) + rng.normal(0, 0.05, n_days)

    # Monthly export commodity basket: procyclical, sampled month-start.
    months = pd.date_range(start=idx[0].normalize().replace(day=1), end=idx[-1], freq="MS")
    risk_monthly = pd.Series(risk, index=idx).reindex(months, method="ffill").to_numpy()
    basket_ret = 0.02 * np.diff(np.concatenate([[risk_monthly[0]], risk_monthly])) + rng.normal(0, 0.02, len(months))
    commodity_basket = pd.Series(100 * np.exp(np.cumsum(basket_ret)), index=months, name="commodity_basket")

    # Market short %: mean-reverting ~5%, rises (more shorts) in risk-off.
    short = np.empty(n_days); short[0] = 5.0
    for t in range(1, n_days):
        short[t] = short[t - 1] + 0.02 * (5.0 - short[t - 1]) - 0.03 * d_risk[t] + rng.normal(0, 0.03)
    short_pct = pd.Series(short, index=idx, name="short_pct").clip(lower=1.0)

    return {
        "audusd": audusd,
        "cgs_10y_yield": cgs_10y,
        "cgs_2y_yield": cgs_2y,
        "hy_oas": hy_oas,
        "commodity_basket": commodity_basket,
        "short_pct": short_pct,
    }
