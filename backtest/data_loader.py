"""
Module 1 — Data Loader for Portfolio Scanner V5 Backtester

Loads daily bar data from two sources into unified pandas DataFrames:
  1. TradingView CSV exports  (Date, Open, High, Low, Close, [Volume])
  2. Sierra Chart .dly files  (binary: Date, O, H, L, C, Vol, NumTrades, OI)

Output schema per symbol:
  Index : DatetimeIndex (timezone-naive, daily)
  Columns: Open, High, Low, Close, Volume, OpenInterest
"""

import struct
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Column contract ──────────────────────────────────────────────────────────
COLUMNS = ["Open", "High", "Low", "Close", "Volume", "OpenInterest"]

# ── Sierra Chart .dly binary format ──────────────────────────────────────────
# Each record: 32 bytes, no file header
#   int32   Date         (YYYYMMDD)
#   float32 Open
#   float32 High
#   float32 Low
#   float32 Close
#   uint32  Volume
#   uint32  NumTrades
#   uint32  OpenInterest
_DLY_STRUCT = struct.Struct("<i4f3I")  # little-endian: 1 int32, 4 float32, 3 uint32
_DLY_RECORD_SIZE = _DLY_STRUCT.size    # 32 bytes


def _parse_dly_date(yyyymmdd: int) -> datetime:
    """Convert Sierra Chart integer date to datetime."""
    y = yyyymmdd // 10000
    m = (yyyymmdd % 10000) // 100
    d = yyyymmdd % 100
    return datetime(y, m, d)


def load_dly(filepath: Path) -> pd.DataFrame:
    """Load a Sierra Chart .dly binary file into a DataFrame."""
    filepath = Path(filepath)
    raw = filepath.read_bytes()

    if len(raw) == 0:
        raise ValueError(f"Empty .dly file: {filepath}")
    if len(raw) % _DLY_RECORD_SIZE != 0:
        raise ValueError(
            f"{filepath}: file size {len(raw)} is not a multiple of "
            f"record size {_DLY_RECORD_SIZE}"
        )

    n_records = len(raw) // _DLY_RECORD_SIZE
    rows = []
    for i in range(n_records):
        offset = i * _DLY_RECORD_SIZE
        date_int, o, h, l, c, vol, _num_trades, oi = _DLY_STRUCT.unpack_from(raw, offset)

        # Skip obviously invalid records (date=0 or price=0)
        if date_int <= 0 or c <= 0:
            continue

        rows.append({
            "Date": _parse_dly_date(date_int),
            "Open": float(o),
            "High": float(h),
            "Low": float(l),
            "Close": float(c),
            "Volume": int(vol),
            "OpenInterest": int(oi),
        })

    if not rows:
        raise ValueError(f"No valid records in {filepath}")

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df[COLUMNS]


# ── TradingView CSV ─────────────────────────────────────────────────────────
# TradingView exports vary slightly. Common column names:
#   "time"/"Date"  |  "open"/"Open"  |  "high"  |  "low"  |  "close"  |  "Volume"/"volume"
_TV_COL_MAP = {
    "time": "Date",
    "date": "Date",
    "datetime": "Date",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
    "vol": "Volume",
}


def load_csv(filepath: Path) -> pd.DataFrame:
    """Load a TradingView CSV export into a DataFrame."""
    filepath = Path(filepath)
    df = pd.read_csv(filepath)

    # Normalize column names: lowercase then map
    df.columns = df.columns.str.strip()
    rename = {}
    for col in df.columns:
        mapped = _TV_COL_MAP.get(col.lower())
        if mapped and mapped not in rename.values():
            rename[col] = mapped
    df = df.rename(columns=rename)

    # Require minimum columns
    for required in ("Date", "Open", "High", "Low", "Close"):
        if required not in df.columns:
            raise ValueError(
                f"{filepath}: missing required column '{required}'. "
                f"Found: {list(df.columns)}"
            )

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()

    # Fill optional columns
    if "Volume" not in df.columns:
        df["Volume"] = 0
    if "OpenInterest" not in df.columns:
        df["OpenInterest"] = 0

    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype(int)
    df["OpenInterest"] = pd.to_numeric(df["OpenInterest"], errors="coerce").fillna(0).astype(int)

    return df[COLUMNS]


# ── Ticker extraction from filename ─────────────────────────────────────────

# Symbols that should NOT be extracted by splitting on common separators.
# "MA" is Mastercard but also collides with "Moving Average" in some file names.
# If a file is literally named "MA.csv" or "MA.dly" we keep it.
# If it's "AAPL_MA_50.csv" (a moving-average export), we skip it.
_MA_FALSE_POSITIVE_PATTERNS = {"_MA_", "_MA.", " MA ", " MA."}


_STRIP_SUFFIXES = (
    "_daily", "_Daily", "_DAILY",
    "_weekly", "_Weekly", "_WEEKLY",
    " daily", " Daily", " DAILY",
    ", daily", ", Daily", ", DAILY",
    "-daily", "-Daily", "-DAILY",
)


def _ticker_from_filename(filepath: Path) -> str:
    """
    Extract ticker symbol from a data file name.

    Handles common patterns:
      AAPL.csv          -> AAPL
      AAPL_daily.csv    -> AAPL
      MSFT, Daily.csv   -> MSFT
      ES_F.dly          -> ES_F  (underscore is part of futures ticker)
      MA.csv            -> MA    (Mastercard — kept as-is)
      AAPL_MA_50.csv    -> skip  (moving-average export, not price data)
    """
    stem = filepath.stem  # filename without extension

    # If stem is exactly "MA" (case-insensitive), it's Mastercard
    if stem.upper() == "MA":
        return "MA"

    # Check for MA false-positive patterns (moving-average files, not Mastercard)
    for pattern in _MA_FALSE_POSITIVE_PATTERNS:
        if pattern in f"_{stem}.":
            return ""  # signal to skip this file

    # Strip known non-ticker suffixes (preserves underscores in tickers like ES_F)
    ticker = stem
    for suffix in _STRIP_SUFFIXES:
        if ticker.endswith(suffix):
            ticker = ticker[: -len(suffix)]
            break

    # If comma-separated (e.g. "MSFT, Daily"), take first part
    if "," in ticker:
        ticker = ticker.split(",")[0].strip()

    return ticker.strip().upper()


# ── Bulk loader ──────────────────────────────────────────────────────────────

def load_directory(
    directory: str | Path,
    extensions: tuple[str, ...] = (".csv", ".dly"),
) -> dict[str, pd.DataFrame]:
    """
    Scan a directory for CSV and .dly files, load each into a DataFrame.

    Returns:
        dict mapping ticker symbol -> DataFrame

    Handles:
        - Mixed CSV + .dly files
        - MA ticker disambiguation
        - Duplicate tickers: .dly wins (has OpenInterest); warns on conflict
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Data directory not found: {directory}")

    found: dict[str, tuple[Path, pd.DataFrame]] = {}
    skipped: list[str] = []

    files = sorted(directory.iterdir())
    for fp in files:
        if not fp.is_file():
            continue
        suffix = fp.suffix.lower()
        if suffix not in extensions:
            continue

        ticker = _ticker_from_filename(fp)
        if not ticker:
            skipped.append(fp.name)
            continue

        try:
            if suffix == ".dly":
                df = load_dly(fp)
            else:
                df = load_csv(fp)
        except Exception as e:
            print(f"  WARN: skipping {fp.name}: {e}")
            skipped.append(fp.name)
            continue

        # Dedup: .dly takes priority (has OI); otherwise first file wins
        if ticker in found:
            existing_path, _ = found[ticker]
            if suffix == ".dly" and existing_path.suffix.lower() != ".dly":
                print(f"  INFO: {ticker}: .dly overrides CSV ({existing_path.name} -> {fp.name})")
                found[ticker] = (fp, df)
            else:
                print(f"  WARN: duplicate ticker '{ticker}': keeping {existing_path.name}, skipping {fp.name}")
        else:
            found[ticker] = (fp, df)

    data = {ticker: df for ticker, (_, df) in found.items()}

    if skipped:
        print(f"\n  Skipped {len(skipped)} file(s): {', '.join(skipped)}")

    return data


# ── Summary stats ────────────────────────────────────────────────────────────

def print_summary(data: dict[str, pd.DataFrame]) -> None:
    """Print a concise summary of loaded data."""
    if not data:
        print("No data loaded.")
        return

    print(f"\n{'='*70}")
    print(f" PORTFOLIO SCANNER V5 — DATA SUMMARY")
    print(f"{'='*70}")
    print(f" Symbols loaded: {len(data)}")
    print(f"{'─'*70}")
    print(f" {'Ticker':<10} {'Rows':>6} {'Start':>12} {'End':>12} {'Vol>0':>6} {'OI>0':>6} {'Source'}")
    print(f"{'─'*70}")

    total_rows = 0
    for ticker in sorted(data.keys()):
        df = data[ticker]
        n = len(df)
        total_rows += n
        start = df.index.min().strftime("%Y-%m-%d")
        end = df.index.max().strftime("%Y-%m-%d")
        has_vol = (df["Volume"] > 0).sum()
        has_oi = (df["OpenInterest"] > 0).sum()
        # Infer source from OI coverage
        source = "DLY" if has_oi > n * 0.1 else "CSV"
        print(f" {ticker:<10} {n:>6,} {start:>12} {end:>12} {has_vol:>6,} {has_oi:>6,} {source}")

    print(f"{'─'*70}")
    print(f" Total: {len(data)} symbols, {total_rows:,} bars")
    print(f"{'='*70}\n")


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python data_loader.py <data_directory>")
        print("  Example: python data_loader.py 'C:\\Users\\Trader\\OneDrive\\Desktop\\NEW DATA'")
        sys.exit(1)

    data_dir = sys.argv[1]
    print(f"Loading data from: {data_dir}")
    data = load_directory(data_dir)
    print_summary(data)
