"""Synthetic Phase 0 inputs, so the full pipeline runs without network access.

This is for development and for the offline demo only. It generates plausible-
looking XJO, AUD/USD and 10y CGS yield series with realistic autocorrelation and
a volatility regime, so the engine, compositing and labelling can be exercised
end to end. It is NOT a data source for the product.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_inputs(
    n_days: int = 1000,
    seed: int = 7,
    start: str = "2021-01-01",
) -> dict[str, pd.Series]:
    """Return synthetic {'xjo_close', 'audusd', 'cgs_10y_yield'} over trading days."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n_days)

    # A slow-moving volatility regime so realised vol actually varies.
    base_vol = 0.008
    regime = 1.0 + 0.8 * np.sin(np.linspace(0, 6 * np.pi, n_days)) ** 2
    daily_vol = base_vol * regime

    # XJO: drifting geometric random walk with the regime vol, plus one shock.
    shocks = rng.normal(0, 1, n_days) * daily_vol + 0.0002
    shocks[int(n_days * 0.6) : int(n_days * 0.6) + 15] -= 0.012  # a fear episode
    xjo = pd.Series(7000 * np.exp(np.cumsum(shocks)), index=idx, name="xjo_close")

    # AUD/USD: risk-on currency, correlated with equity shocks.
    aud_shocks = 0.6 * shocks + 0.4 * rng.normal(0, 0.004, n_days)
    audusd = pd.Series(0.72 * np.exp(np.cumsum(aud_shocks)), index=idx, name="audusd")

    # 10y CGS yield: mean-reverting around ~4%, falls when equities fall (flight to safety).
    yld = np.empty(n_days)
    yld[0] = 4.0
    for t in range(1, n_days):
        pull = 0.01 * (4.0 - yld[t - 1])
        flight = 8.0 * shocks[t]  # yields drop when equities drop
        yld[t] = yld[t - 1] + pull + flight + rng.normal(0, 0.02)
    cgs = pd.Series(yld, index=idx, name="cgs_10y_yield").clip(lower=0.25)

    return {"xjo_close": xjo, "audusd": audusd, "cgs_10y_yield": cgs}
