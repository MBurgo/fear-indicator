"""ASIC aggregated short-position data (spec section 3.5).

ASIC publishes a daily file of aggregated short positions per ASX product, with a
~4 business-day lag. Each file lists, per stock, the reported short positions, the
total quantity on issue, and the short percentage. We aggregate these into a
single market-wide short ratio per date, then build a time series.

The published files are notoriously fiddly (tab-delimited, sometimes UTF-16, a
header row, column names that vary slightly), so the parser is deliberately
tolerant: it sniffs delimiter/encoding and matches columns by fuzzy name. Live
ingestion reads a local directory of downloaded ASIC files (the reliable path);
see docs for where to get them. The aggregation logic is fully unit-tested.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

_DATE_RE = re.compile(r"(\d{8})")


def _read_tabular(raw: bytes | str) -> pd.DataFrame:
    """Read an ASIC file (bytes or text), sniffing encoding and delimiter."""
    if isinstance(raw, bytes):
        for enc in ("utf-16", "utf-8-sig", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("latin-1", errors="replace")
    else:
        text = raw
    last_err: Exception | None = None
    for sep in ("\t", ",", ";"):
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, engine="python")
            if df.shape[1] >= 3:
                return df
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise ValueError(f"Could not parse ASIC tabular data: {last_err}")


def _find_col(columns, *needles: str) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    for needle in needles:
        for lc, orig in lower.items():
            if needle in lc:
                return orig
    return None


def parse_aggregate_file(raw: bytes | str) -> pd.DataFrame:
    """Parse one ASIC daily aggregate file -> DataFrame[code, short, issue, pct]."""
    df = _read_tabular(raw)
    code_col = _find_col(df.columns, "product code", "asx code", "code")
    short_col = _find_col(df.columns, "reported short positions", "reported short", "short positions")
    issue_col = _find_col(df.columns, "total product in issue", "total product", "in issue")
    pct_col = _find_col(df.columns, "% of total", "percent", "% reported")
    if short_col is None or issue_col is None:
        raise ValueError(f"ASIC file missing expected columns; got {list(df.columns)}")
    out = pd.DataFrame(
        {
            "code": df[code_col].astype(str).str.strip() if code_col else "",
            "short": pd.to_numeric(df[short_col], errors="coerce"),
            "issue": pd.to_numeric(df[issue_col], errors="coerce"),
        }
    )
    if pct_col is not None:
        out["pct"] = pd.to_numeric(df[pct_col], errors="coerce")
    return out.dropna(subset=["short", "issue"])


def market_short_pct(df: pd.DataFrame, min_issue: float = 0.0) -> float:
    """Aggregate one day's file into a market-wide short ratio (percent).

    Issued-capital weighted: sum(reported short) / sum(total on issue). This is
    naturally dominated by larger, more liquid names; ``min_issue`` can drop the
    micro-cap tail explicitly.
    """
    f = df[df["issue"] >= min_issue] if min_issue else df
    total_issue = f["issue"].sum()
    if total_issue <= 0:
        return float("nan")
    return 100.0 * f["short"].sum() / total_issue


def _date_from_name(name: str) -> pd.Timestamp | None:
    m = _DATE_RE.search(name)
    if not m:
        return None
    return pd.to_datetime(m.group(1), format="%Y%m%d", errors="coerce")


def build_short_series_from_dir(
    directory: str | Path,
    pattern: str = "*.csv",
    min_issue: float = 0.0,
) -> pd.Series:
    """Build a market-wide short-% series from a directory of ASIC daily files.

    The report date is taken from the YYYYMMDD in each filename. Returns a daily
    Series (percent), sorted ascending.
    """
    directory = Path(directory)
    rows: dict[pd.Timestamp, float] = {}
    for path in sorted(directory.glob(pattern)):
        date = _date_from_name(path.name)
        if date is None or pd.isna(date):
            continue
        try:
            df = parse_aggregate_file(path.read_bytes())
            rows[date] = market_short_pct(df, min_issue=min_issue)
        except Exception:  # noqa: BLE001 - skip an unparseable day, keep the rest
            continue
    if not rows:
        raise RuntimeError(f"No parseable ASIC files found in {directory}")
    s = pd.Series(rows, name="short_pct").sort_index()
    return s.dropna()
