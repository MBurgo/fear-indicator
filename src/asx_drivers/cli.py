"""Command-line runner for the Phase 0 ASX Drivers Index.

Usage:
    python -m asx_drivers.cli --source synthetic         # offline demo, no network
    python -m asx_drivers.cli --source live              # fetch RBA + FRED (keyless)
    python -m asx_drivers.cli --source live --json web/data.json

The 'live' source needs outbound access to www.rba.gov.au and
fred.stlouisfed.org. Both are institutional, keyless and script-friendly.
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from . import TAGLINE, TITLE
from . import index as idx_mod
from .data import align
from asx_mood.composite import DRIVERS_LABELS, calibrate_band_edges, latest_reading

COMPONENT_LABELS = {
    "commodity": "Commodity complex",
    "aud": "AUD risk flow",
    "curve_slope": "Yield-curve slope",
    "credit_risk": "Global credit risk",
    "short_positioning": "Short positioning",
}

# Daily series that must align onto a common calendar before the engine runs.
DAILY_KEYS = ["audusd", "cgs_10y_yield", "cgs_2y_yield", "hy_oas"]

# Thresholds (component score) for calling a component a tailwind / headwind.
TAILWIND_AT = 55.0
HEADWIND_AT = 45.0

# Retained for the legacy --fixed-bands path only.
LABEL_MAP = {
    "Extreme Fear": "Strong Headwind",
    "Fear": "Headwind",
    "Neutral": "Neutral",
    "Greed": "Tailwind",
    "Extreme Greed": "Strong Tailwind",
}


def _load_live(asic_dir: str | None = None) -> dict[str, object]:
    from asx_mood.data import rba

    from .data import asic, fred

    basket, weights, errors = fred.build_commodity_basket()
    if errors:
        print(f"  commodity basket: loaded {list(weights)}; skipped {len(errors)} leg(s)")

    inputs: dict[str, object] = {
        "audusd": rba.load_audusd(),
        "cgs_10y_yield": rba.load_cgs_10y_yield(),
        "cgs_2y_yield": rba.load_cgs_2y_yield(),
        "hy_oas": fred.load_hy_oas(),
        "commodity_basket": basket,
        "short_pct": None,
    }
    if asic_dir:
        sp = asic.build_short_series_from_dir(asic_dir)
        inputs["short_pct"] = sp
        span = f"{sp.index.min().date()}..{sp.index.max().date()}" if len(sp) else "empty"
        print(f"  short positioning: {len(sp)} days ({span}) from {asic_dir}")
    return inputs


def _load_synthetic() -> dict[str, object]:
    from .data.synthetic import make_inputs

    return make_inputs()


def divergence_summary(components: dict[str, float]) -> str:
    """A one-line plain-English read of which drivers help vs hurt."""
    tail = [COMPONENT_LABELS.get(k, k) for k, v in components.items() if v >= TAILWIND_AT]
    head = [COMPONENT_LABELS.get(k, k) for k, v in components.items() if v <= HEADWIND_AT]
    parts = []
    if tail:
        parts.append("Tailwinds: " + ", ".join(tail))
    if head:
        parts.append("Headwinds: " + ", ".join(head))
    return ". ".join(parts) if parts else "Drivers are broadly balanced."


def run(args: argparse.Namespace) -> int:
    frames = _load_synthetic() if args.source == "synthetic" else _load_live(args.asic_dir)

    daily = align({k: frames[k] for k in DAILY_KEYS}).dropna()

    scores, composite_idx = idx_mod.build(
        daily["audusd"],
        daily["cgs_10y_yield"],
        daily["cgs_2y_yield"],
        daily["hy_oas"],
        frames["commodity_basket"],
        short_pct=frames.get("short_pct"),
        window=args.window,
        min_periods=args.min_periods,
    )

    # Stable, distribution-calibrated band edges with hysteresis (preferred), or
    # the spec's fixed 0-100 bands via --fixed-bands.
    edges = calibrate_band_edges(composite_idx)
    if args.fixed_bands:
        reading = latest_reading(scores, composite_idx, calibrate=False)
        label = LABEL_MAP.get(reading.label, reading.label)
    else:
        reading = latest_reading(
            scores, composite_idx, edges=edges, names=DRIVERS_LABELS
        )
        label = reading.label
    summary = divergence_summary(reading.components)

    print(f"\n  {TITLE} - {reading.date}")
    print(f"  {'=' * 38}")
    print(f"  Score: {reading.score:>3}/100   {label}")
    print(f"  {'-' * 38}")
    for name, val in reading.components.items():
        bar = "#" * int(round(val / 5))
        print(f"  {COMPONENT_LABELS.get(name, name):<20} {val:>5.1f}  {bar}")
    print(f"  {'-' * 38}")
    print(f"  {summary}")
    print()

    if args.json:
        payload = reading.to_dict()
        payload["label"] = label
        payload["title"] = TITLE
        payload["tagline"] = TAGLINE
        payload["lowLabel"] = "Headwind"
        payload["highLabel"] = "Tailwind"
        payload["summary"] = summary
        payload["bandEdges"] = edges
        payload["bandLabels"] = DRIVERS_LABELS
        payload["history"] = [
            {"date": d.strftime("%Y-%m-%d"), "score": round(float(v), 1)}
            for d, v in composite_idx.dropna().items()
        ]
        with open(args.json, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"  wrote {args.json}")

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ASX Drivers Index (Phase 0)")
    p.add_argument(
        "--source",
        choices=["synthetic", "live"],
        default="synthetic",
        help="synthetic (offline demo) or live (fetch RBA + FRED)",
    )
    p.add_argument(
        "--asic-dir",
        dest="asic_dir",
        default=None,
        help="directory of downloaded ASIC daily short-position files (adds the "
        "short-positioning component)",
    )
    p.add_argument("--window", type=int, default=252, help="normalisation window (days)")
    p.add_argument(
        "--min-periods",
        dest="min_periods",
        type=int,
        default=None,
        help="min observations before a score is emitted (default = window)",
    )
    p.add_argument(
        "--fixed-bands",
        action="store_true",
        help="use fixed 0-100 label bands instead of calibrated percentiles",
    )
    p.add_argument("--json", help="write reading + history to this JSON path")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
