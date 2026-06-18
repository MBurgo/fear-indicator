"""Synthetic Phase 0 inputs for the ASX Drivers Index (offline demo + tests).

Generates plausible AUD/USD, 2y & 10y CGS yields, US high-yield credit spread,
and gold series with realistic autocorrelation and a risk-off episode, so the
engine, compositing and front end can be exercised without network access. NOT a
data source for the product.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_inputs(
    n_days: int = 1000,
    seed: int = 11,
    start: str = "2021-01-01",
) -> dict[str, pd.Series]:
    """Return synthetic Phase 0 driver inputs over trading days."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n_days)

    # A latent global risk factor: positive = risk-on, with one risk-off episode.
    risk = np.cumsum(rng.normal(0, 1, n_days) * 0.05)
    shock_lo = int(n_days * 0.6)
    risk[shock_lo : shock_lo + 20] -= np.linspace(0, 3.0, 20)

    # AUD/USD: rises with risk-on.
    aud_ret = 0.0006 * np.diff(np.concatenate([[risk[0]], risk])) + rng.normal(0, 0.003, n_days)
    audusd = pd.Series(0.72 * np.exp(np.cumsum(aud_ret)), index=idx, name="audusd")

    # Gold: mild safe-haven + trend; partial negative correlation to risk.
    gold_ret = -0.0004 * np.diff(np.concatenate([[risk[0]], risk])) + 0.0002 + rng.normal(0, 0.006, n_days)
    gold = pd.Series(1800 * np.exp(np.cumsum(gold_ret)), index=idx, name="gold")

    # 10y CGS yield: mean-reverting ~4%, falls in risk-off (flight to safety).
    y10 = np.empty(n_days)
    y10[0] = 4.0
    for t in range(1, n_days):
        y10[t] = y10[t - 1] + 0.01 * (4.0 - y10[t - 1]) + 0.03 * (risk[t] - risk[t - 1]) + rng.normal(0, 0.02)
    cgs_10y = pd.Series(y10, index=idx, name="cgs_10y_yield").clip(lower=0.25)

    # 2y CGS yield: tracks short-rate expectations; curve flattens/inverts in stress.
    y2 = np.empty(n_days)
    y2[0] = 3.2
    for t in range(1, n_days):
        y2[t] = y2[t - 1] + 0.01 * (3.4 - y2[t - 1]) + 0.05 * (risk[t] - risk[t - 1]) + rng.normal(0, 0.02)
    cgs_2y = pd.Series(y2, index=idx, name="cgs_2y_yield").clip(lower=0.1)

    # US HY OAS (percent): low in risk-on, spikes in risk-off.
    hy = 3.5 - 0.25 * risk
    hy[shock_lo : shock_lo + 25] += np.linspace(0, 4.0, 25)
    hy_oas = pd.Series(hy, index=idx, name="hy_oas").clip(lower=2.0) + rng.normal(0, 0.05, n_days)

    return {
        "audusd": audusd,
        "gold": gold,
        "cgs_10y_yield": cgs_10y,
        "cgs_2y_yield": cgs_2y,
        "hy_oas": hy_oas,
    }
