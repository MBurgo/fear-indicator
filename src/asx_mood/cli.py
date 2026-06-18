"""Command-line runner for the Phase 0 ASX Mood Index.

Usage:
    python -m asx_mood.cli --source synthetic        # offline demo, no network
    python -m asx_mood.cli --source live             # fetch RBA + free XJO
    python -m asx_mood.cli --source live --json out.json --history hist.csv

The 'live' source needs outbound access to the RBA and the free XJO host. In a
restricted cloud session those hosts must be on the egress allowlist; locally
they just work.
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from . import index as idx_mod
from .composite import latest_reading
from .data import align


def _load_live(xjo_source: str = "auto") -> dict[str, pd.Series]:
    from .data import rba, xjo

    return {
        "xjo_close": xjo.load_xjo_close(source=xjo_source),
        "audusd": rba.load_audusd(),
        "cgs_10y_yield": rba.load_cgs_10y_yield(),
    }


def _load_synthetic() -> dict[str, pd.Series]:
    from .data.synthetic import make_inputs

    return make_inputs()


def run(args: argparse.Namespace) -> int:
    frames = (
        _load_synthetic()
        if args.source == "synthetic"
        else _load_live(args.xjo_source)
    )
    df = align(frames).dropna()

    scores, composite_idx = idx_mod.build(
        df["xjo_close"],
        df["audusd"],
        df["cgs_10y_yield"],
        window=args.window,
        min_periods=args.min_periods,
    )

    reading = latest_reading(scores, composite_idx, calibrate=not args.fixed_bands)

    print(f"\n  ASX Mood Index - {reading.date}")
    print(f"  {'=' * 34}")
    print(f"  Score: {reading.score:>3}/100   {reading.label}")
    print(f"  {'-' * 34}")
    for name, val in reading.components.items():
        bar = "#" * int(round(val / 5))
        print(f"  {name:<12} {val:>5.1f}  {bar}")
    print()

    if args.json:
        payload = reading.to_dict()
        payload["history"] = [
            {"date": d.strftime("%Y-%m-%d"), "score": round(float(v), 1)}
            for d, v in composite_idx.dropna().items()
        ]
        with open(args.json, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"  wrote {args.json}")

    if args.history:
        composite_idx.dropna().rename("score").to_csv(args.history)
        print(f"  wrote {args.history}")

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ASX Mood Index (Phase 0)")
    p.add_argument(
        "--source",
        choices=["synthetic", "live"],
        default="synthetic",
        help="synthetic (offline demo) or live (fetch RBA + free XJO)",
    )
    p.add_argument(
        "--xjo-source",
        dest="xjo_source",
        choices=["auto", "stooq", "yahoo"],
        default="auto",
        help="free XJO source for live runs (auto tries stooq then yahoo)",
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
        help="use the spec's fixed 0-100 label bands instead of calibrated percentiles",
    )
    p.add_argument("--json", help="write reading + history to this JSON path")
    p.add_argument("--history", help="write composite history to this CSV path")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
