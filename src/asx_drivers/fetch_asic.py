"""Fetch ASIC daily aggregated short-position files into a local directory.

Usage:
    python -m asx_drivers.fetch_asic --out ~/asic
    python -m asx_drivers.fetch_asic --out ~/asic --start 2023-01-01

ASIC publishes one aggregated short-position file per trading day, ~4 business
days in arrears, as a UTF-16, tab-delimited CSV. This downloads the files across
a date range so the ``--asic-dir`` short-positioning component can be built.

Robustness: ASIC's exact URL has changed over time, so several candidate URL
patterns are tried per date, and every download is validated by parsing it as an
ASIC aggregate file before saving. If the first several days all fail, the run
aborts with the URLs it tried, so you can paste the real URL from ASIC's
short-selling reports page and the template can be corrected. Files already
present are skipped (resumable).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

from .data import asic

# Confirmed ASIC download URL (flat short-selling path). {d}=YYYYMMDD.
URL_TEMPLATES = (
    "https://download.asic.gov.au/short-selling/RR{d}-001-SSDailyAggShortPos.csv",
)
FILENAME_TMPL = "RR{d}-001-SSDailyAggShortPos.csv"

_TIMEOUT = 30
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def urls_for(date: pd.Timestamp) -> list[str]:
    d = date.strftime("%Y%m%d")
    return [t.format(d=d) for t in URL_TEMPLATES]


_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def _get(url: str, attempts: int = 3) -> requests.Response | None:
    """GET with retries on transient failures (timeouts, throttling, 5xx/429)."""
    for k in range(attempts):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        except requests.RequestException:
            time.sleep(0.5 * (k + 1))
            continue
        if resp.status_code in _TRANSIENT_STATUS:
            time.sleep(0.5 * (k + 1))
            continue
        return resp
    return None


def _try_download(date: pd.Timestamp) -> tuple[bytes | None, str]:
    """Return (file bytes, reason). bytes is None on failure; reason explains why."""
    reasons = []
    for url in urls_for(date):
        resp = _get(url)
        if resp is None:
            reasons.append("no-response")
            continue
        if resp.status_code != 200 or not resp.content:
            reasons.append(f"HTTP {resp.status_code}")
            continue
        try:
            asic.parse_aggregate_file(resp.content)  # validate it really is one
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"200-unparseable ({str(exc)[:40]})")
            continue
        return resp.content, "ok"
    return None, "; ".join(reasons) or "fail"


def fetch_range(
    start: pd.Timestamp,
    end: pd.Timestamp,
    out_dir: str | Path,
    delay: float = 0.2,
    abort_after: int = 12,
    verbose: bool = False,
) -> int:
    """Download ASIC files across [start, end] into ``out_dir``. Returns count saved."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    days = pd.bdate_range(start, end)
    saved = skipped = missed = 0
    consecutive_miss = 0
    # If files already exist we know the URL pattern works, so don't early-abort
    # on a resumable top-up (the remaining dates are the known-hard ones).
    any_success = bool(list(out.glob("RR*SSDailyAggShortPos.csv")))
    last_tried = ""
    miss_reasons: Counter[str] = Counter()

    for date in days:
        dest = out / FILENAME_TMPL.format(d=date.strftime("%Y%m%d"))
        if dest.exists():
            skipped += 1
            continue
        last_tried = urls_for(date)[0]
        content, reason = _try_download(date)
        if content is not None:
            dest.write_bytes(content)
            saved += 1
            any_success = True
            consecutive_miss = 0
        else:
            missed += 1
            consecutive_miss += 1
            miss_reasons[reason.split(" (")[0]] += 1
            if verbose:
                print(f"  MISS {date.date()}: {reason}")
        if not any_success and consecutive_miss >= abort_after:
            print(
                f"Aborting: the first {abort_after} downloads all failed - ASIC's "
                f"URL pattern may have changed.\n  Tried e.g. {last_tried}"
            )
            return saved
        time.sleep(delay)

    print(f"saved {saved}, skipped {skipped} (already present), missed {missed} -> {out}")
    if miss_reasons:
        print(f"  miss reasons: {dict(miss_reasons)}")
    return saved


def inspect_first_missing(out_dir: str | Path, start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Download the first missing date's file and dump bytes/encoding/parse error."""
    out = Path(out_dir)
    for date in pd.bdate_range(start, end):
        dest = out / FILENAME_TMPL.format(d=date.strftime("%Y%m%d"))
        if dest.exists():
            continue
        url = urls_for(date)[0]
        resp = _get(url)
        print(f"date {date.date()}  url {url}")
        if resp is None:
            print("  no response")
            return 0
        print(f"  status {resp.status_code}  bytes {len(resp.content)}")
        print(f"  raw head: {resp.content[:120]!r}")
        for enc in ("utf-16", "utf-8-sig", "latin-1"):
            try:
                preview = resp.content[:300].decode(enc, errors="replace").replace("\n", "\\n")
                print(f"  [{enc}] {preview[:200]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [{enc}] decode failed: {exc}")
        try:
            df = asic.parse_aggregate_file(resp.content)
            print(f"  parse OK, columns: {list(df.columns)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  parse error: {exc}")
        return 0
    print("No missing dates found in range.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch ASIC daily short-position files")
    p.add_argument("--out", required=True, help="output directory for the files")
    p.add_argument("--start", default=None, help="start date YYYY-MM-DD (default: ~2y before end)")
    p.add_argument("--end", default=None, help="end date YYYY-MM-DD (default: today - 4 business days)")
    p.add_argument("--delay", type=float, default=0.2, help="seconds between requests (politeness)")
    p.add_argument("--verbose", action="store_true", help="print a reason for each missed date")
    p.add_argument("--inspect", action="store_true", help="dump the first missing file for debugging")
    args = p.parse_args(argv)

    # ASIC files appear ~4 business days after their reporting date.
    end = (
        pd.Timestamp(args.end)
        if args.end
        else pd.Timestamp.today().normalize() - pd.tseries.offsets.BusinessDay(4)
    )
    start = pd.Timestamp(args.start) if args.start else end - pd.DateOffset(years=2)
    if args.inspect:
        return inspect_first_missing(args.out, start, end)
    print(f"Fetching ASIC short-position files {start.date()} .. {end.date()} into {args.out}")
    fetch_range(start, end, args.out, delay=args.delay, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
