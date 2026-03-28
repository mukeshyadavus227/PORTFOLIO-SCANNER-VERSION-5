"""
Data loader for TradingView CSV exports and Sierra Chart .dly files.
"""

import struct
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate


# ---------------------------------------------------------------------------
# TradingView CSV loader
# ---------------------------------------------------------------------------

def load_tradingview_csv(filepath: str | Path) -> pd.DataFrame:
    """Load a TradingView daily OHLCV CSV export into a DataFrame.

    Handles filenames with comma-space (e.g. "AMEX_SPY, 1D.csv").
    Extracts ticker symbol from filename and stores it in df.attrs["ticker"].
    """
    filepath = Path(filepath)
    ticker = _extract_ticker_from_csv(filepath.name)

    df = pd.read_csv(filepath)

    # TradingView exports use "time" or "Date" for the date column
    date_col = _find_date_column(df)
    # TradingView "time" column is often a Unix timestamp (seconds since epoch)
    sample = df[date_col].iloc[0]
    if isinstance(sample, (int, float, np.integer, np.floating)) and sample > 1e8:
        df[date_col] = pd.to_datetime(df[date_col], unit="s")
    else:
        df[date_col] = pd.to_datetime(df[date_col])
    df = df.rename(columns={date_col: "Date"}).set_index("Date").sort_index()

    # Normalize column names
    col_map = {}
    for col in df.columns:
        low = col.strip().lower()
        if low == "open":
            col_map[col] = "Open"
        elif low == "high":
            col_map[col] = "High"
        elif low == "low":
            col_map[col] = "Low"
        elif low == "close":
            col_map[col] = "Close"
        elif low == "volume":
            col_map[col] = "Volume"
    df = df.rename(columns=col_map)

    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[keep]

    df.attrs["ticker"] = ticker
    df.attrs["source"] = "TradingView"
    return df


def _extract_ticker_from_csv(filename: str) -> str:
    """Extract ticker from TradingView filename like 'AMEX_SPY, 1D.csv'."""
    name = filename.replace(".csv", "")
    # Strip timeframe suffix after comma: "AMEX_SPY, 1D" -> "AMEX_SPY"
    if "," in name:
        name = name.split(",")[0].strip()
    # Strip exchange prefix: "AMEX_SPY" -> "SPY", "CME_MINI_NQM2026" -> "NQM2026"
    parts = name.split("_")
    # Known exchange prefixes
    exchanges = {"AMEX", "NYSE", "NASDAQ", "CME", "NYMEX", "COMEX", "CBOT", "CBOE",
                 "FOREX", "FX", "OANDA", "CURRENCYCOM", "INDEX", "TVC", "CAPITALCOM"}
    # Also handle compound prefixes like CME_MINI
    modifiers = {"MINI", "MICRO", "E"}
    filtered = []
    prefix_done = False
    for part in parts:
        if not prefix_done and part.upper() in exchanges:
            continue
        if not prefix_done and part.upper() in modifiers:
            continue
        prefix_done = True
        filtered.append(part)
    return "_".join(filtered) if filtered else name


def _find_date_column(df: pd.DataFrame) -> str:
    """Find the date/time column in a DataFrame."""
    for col in df.columns:
        low = col.strip().lower()
        if low in ("time", "date", "datetime", "timestamp"):
            return col
    # Fallback: first column
    return df.columns[0]


# ---------------------------------------------------------------------------
# Sierra Chart .dly loader
# ---------------------------------------------------------------------------

# Sierra Chart .dly binary record:
#   4 bytes: date as int (YYYYMMDD in SC Julian or Excel-style)
#   4 x float32: Open, High, Low, Close
#   4 bytes uint32: Volume
#   4 bytes uint32: OpenInterest
# Total: 28 bytes per record (old format)
#
# Newer SC format uses 40-byte records with int64 volume/OI.
_RECORD_28 = struct.Struct("<I 4f I I")       # 28 bytes
_RECORD_40 = struct.Struct("<I 4f I I 4x 4x")  # 40 bytes (extra padding)
_RECORD_56 = struct.Struct("<I 4f Q Q 20x")    # 56 bytes (int64 vol/OI + pad)


def load_sierra_dly(filepath: str | Path) -> pd.DataFrame:
    """Load a Sierra Chart .dly file into a DataFrame.

    Tries binary parsing first; falls back to CSV if binary fails.
    """
    filepath = Path(filepath)
    ticker = filepath.stem  # e.g. "ES" from "ES.dly"

    data = filepath.read_bytes()

    # Try binary parse
    df = _try_binary_dly(data)
    if df is not None:
        df.attrs["ticker"] = ticker
        df.attrs["source"] = "SierraChart"
        return df

    # Fallback: try as CSV
    df = _try_csv_dly(filepath)
    df.attrs["ticker"] = ticker
    df.attrs["source"] = "SierraChart"
    return df


def _sc_date_to_datetime(date_int: int) -> datetime | None:
    """Convert a Sierra Chart date integer to a datetime.

    SC uses Excel-style serial dates (days since 1899-12-30)
    or YYYYMMDD format.
    """
    if date_int > 19000101:
        # YYYYMMDD format
        y = date_int // 10000
        m = (date_int % 10000) // 100
        d = date_int % 100
        try:
            return datetime(y, m, d)
        except ValueError:
            return None
    else:
        # Excel serial date (days since 1899-12-30)
        try:
            return datetime(1899, 12, 30) + pd.Timedelta(days=int(date_int))
        except (ValueError, OverflowError):
            return None


def _try_binary_dly(data: bytes) -> pd.DataFrame | None:
    """Attempt to parse .dly as Sierra Chart binary."""
    if len(data) == 0:
        return None

    # Determine record size
    for rec_struct, rec_size in [(_RECORD_28, 28), (_RECORD_56, 56), (_RECORD_40, 40)]:
        if len(data) % rec_size != 0:
            continue
        n_records = len(data) // rec_size
        if n_records == 0:
            continue

        rows = []
        valid = True
        for i in range(n_records):
            chunk = data[i * rec_size: (i + 1) * rec_size]
            try:
                vals = rec_struct.unpack(chunk)
            except struct.error:
                valid = False
                break
            dt = _sc_date_to_datetime(vals[0])
            if dt is None:
                valid = False
                break
            rows.append({
                "Date": dt,
                "Open": vals[1],
                "High": vals[2],
                "Low": vals[3],
                "Close": vals[4],
                "Volume": int(vals[5]),
                "OpenInterest": int(vals[6]),
            })

        if valid and rows:
            df = pd.DataFrame(rows).set_index("Date").sort_index()
            # Sanity check: prices should be positive
            if (df[["Open", "High", "Low", "Close"]] > 0).all().all():
                return df

    return None


def _try_csv_dly(filepath: Path) -> pd.DataFrame:
    """Fallback: parse .dly as a CSV/text file."""
    # Peek at first line to detect header
    first_line = filepath.read_text().split("\n", 1)[0]
    has_header = "Date" in first_line or "date" in first_line

    if has_header:
        df = pd.read_csv(filepath, skipinitialspace=True)
        # Normalize column names (strip whitespace)
        df.columns = [c.strip() for c in df.columns]
    else:
        df = pd.read_csv(filepath, header=None)
        # Assign standard column names
        if df.shape[1] >= 7:
            df.columns = ["Date", "Open", "High", "Low", "Close", "Volume", "OpenInterest"] + \
                          [f"extra_{i}" for i in range(df.shape[1] - 7)]
        elif df.shape[1] >= 5:
            cols = ["Date", "Open", "High", "Low", "Close"]
            if df.shape[1] >= 6:
                cols.append("Volume")
            if df.shape[1] >= 7:
                cols.append("OpenInterest")
            df.columns = cols[:df.shape[1]]
        else:
            raise ValueError(f"Unexpected column count ({df.shape[1]}) in {filepath}")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()

    keep = [c for c in ["Open", "High", "Low", "Close", "Volume", "OpenInterest"] if c in df.columns]
    df = df[keep]
    return df


# ---------------------------------------------------------------------------
# Batch loader
# ---------------------------------------------------------------------------

def load_all_data(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Scan data_dir for .csv and .dly files and load each into a DataFrame.

    Returns a dict keyed by ticker symbol.
    Handles duplicate tickers (e.g. MA appearing twice) by keeping the longer dataset.
    """
    data_dir = Path(data_dir)
    result: dict[str, pd.DataFrame] = {}

    # Load CSVs
    for f in sorted(data_dir.glob("*.csv")):
        try:
            df = load_tradingview_csv(f)
            ticker = df.attrs["ticker"]
            if ticker in result:
                if len(df) > len(result[ticker]):
                    result[ticker] = df
            else:
                result[ticker] = df
        except Exception as e:
            print(f"  WARN: skipping {f.name}: {e}")

    # Load .dly files
    for f in sorted(data_dir.glob("*.dly")):
        try:
            df = load_sierra_dly(f)
            ticker = df.attrs["ticker"]
            if ticker in result:
                if len(df) > len(result[ticker]):
                    result[ticker] = df
            else:
                result[ticker] = df
        except Exception as e:
            print(f"  WARN: skipping {f.name}: {e}")

    return result


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_data_summary(data: dict[str, pd.DataFrame]) -> None:
    """Print a summary table of all loaded datasets."""
    if not data:
        print("No data files found.")
        return

    rows = []
    for ticker in sorted(data.keys()):
        df = data[ticker]
        rows.append({
            "Ticker": ticker,
            "Source": df.attrs.get("source", "unknown"),
            "Start Date": str(df.index.min().date()),
            "End Date": str(df.index.max().date()),
            "Rows": len(df),
            "Has Volume": "Volume" in df.columns,
            "Has OI": "OpenInterest" in df.columns,
        })

    print(tabulate(rows, headers="keys", tablefmt="simple"))
    print(f"\nTotal: {len(data)} tickers loaded")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    data = load_all_data("data/")
    print_data_summary(data)
