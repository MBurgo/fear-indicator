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
from asx_mood.composite import latest_reading

COMPONENT_LABELS = {
    "commodity": "Commodity complex",
    "aud": "AUD risk flow",
    "curve_slope": "Yield-curve slope",
    "credit_risk": "Global credit risk",
}

# This is a conditions gauge, so re-label the shared fear/greed bands as
# headwind/tailwind for an Australian-investor audience.
LABEL_MAP = {
    "Extreme Fear": "Strong Headwind",
    "Fear": "Headwind",
    "Neutral": "Neutral",
    "Greed": "Tailwind",
    "Extreme Greed": "Strong Tailwind",
}


def _load_live() -> dict[str, pd.Series]:
    from asx_mood.data import rba

    from .data import fred

    return {
        "audusd": rba.load_audusd(),
        "commodity": fred.load_commodity(),
        "cgs_10y_yield": rba.load_cgs_10y_yield(),
        "cgs_2y_yield": rba.load_cgs_2y_yield(),
        "hy_oas": fred.load_hy_oas(),
    }


def _load_synthetic() -> dict[str, pd.Series]:
    from .data.synthetic import make_inputs

    return make_inputs()


def run(args: argparse.Namespace) -> int:
    frames = _load_synthetic() if args.source == "synthetic" else _load_live()
    df = align(frames).dropna()

    scores, composite_idx = idx_mod.build(
        df["audusd"],
        df["commodity"],
        df["cgs_10y_yield"],
        df["cgs_2y_yield"],
        df["hy_oas"],
        window=args.window,
        min_periods=args.min_periods,
    )

    reading = latest_reading(scores, composite_idx, calibrate=not args.fixed_bands)
    label = LABEL_MAP.get(reading.label, reading.label)

    print(f"\n  {TITLE} - {reading.date}")
    print(f"  {'=' * 38}")
    print(f"  Score: {reading.score:>3}/100   {label}")
    print(f"  {'-' * 38}")
    for name, val in reading.components.items():
        bar = "#" * int(round(val / 5))
        print(f"  {COMPONENT_LABELS.get(name, name):<20} {val:>5.1f}  {bar}")
    print()

    if args.json:
        payload = reading.to_dict()
        payload["label"] = label
        payload["title"] = TITLE
        payload["tagline"] = TAGLINE
        payload["lowLabel"] = "Headwind"
        payload["highLabel"] = "Tailwind"
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
