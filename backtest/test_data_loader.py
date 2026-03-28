"""
Tests for Module 1 — Data Loader

Creates synthetic CSV and .dly files in a temp directory, loads them,
and validates the unified DataFrame output.
"""

import struct
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from data_loader import (
    COLUMNS,
    _DLY_STRUCT,
    _ticker_from_filename,
    load_csv,
    load_dly,
    load_directory,
    print_summary,
)


def _make_csv(path: Path, rows: int = 100, has_volume: bool = True) -> None:
    """Write a synthetic TradingView-style CSV."""
    lines = []
    if has_volume:
        lines.append("time,open,high,low,close,Volume")
    else:
        lines.append("time,open,high,low,close")

    base = datetime(2023, 1, 3)
    price = 150.0
    for i in range(rows):
        dt = base + timedelta(days=i)
        o = round(price + i * 0.1, 2)
        h = round(o + 2.0, 2)
        l = round(o - 1.0, 2)
        c = round(o + 0.5, 2)
        if has_volume:
            lines.append(f"{dt.strftime('%Y-%m-%d')},{o},{h},{l},{c},{1000000 + i * 1000}")
        else:
            lines.append(f"{dt.strftime('%Y-%m-%d')},{o},{h},{l},{c}")

    path.write_text("\n".join(lines))


def _make_dly(path: Path, rows: int = 100) -> None:
    """Write a synthetic Sierra Chart .dly binary file."""
    base = datetime(2023, 1, 3)
    price = 4000.0
    data = bytearray()
    for i in range(rows):
        dt = base + timedelta(days=i)
        date_int = dt.year * 10000 + dt.month * 100 + dt.day
        o = price + i * 0.5
        h = o + 10.0
        l = o - 5.0
        c = o + 3.0
        vol = 500000 + i * 100
        num_trades = 10000 + i
        oi = 200000 + i * 50
        data.extend(_DLY_STRUCT.pack(date_int, o, h, l, c, vol, num_trades, oi))

    path.write_bytes(bytes(data))


# ── Tests ────────────────────────────────────────────────────────────────────

def test_load_csv_basic():
    """CSV with volume loads correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "AAPL.csv"
        _make_csv(fp, rows=50, has_volume=True)
        df = load_csv(fp)

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == COLUMNS
        assert len(df) == 50
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df["Volume"].sum() > 0
        assert df["OpenInterest"].sum() == 0  # CSV has no OI
        print("  PASS: test_load_csv_basic")


def test_load_csv_no_volume():
    """CSV without volume column fills Volume=0."""
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "MSFT.csv"
        _make_csv(fp, rows=30, has_volume=False)
        df = load_csv(fp)

        assert len(df) == 30
        assert df["Volume"].sum() == 0
        print("  PASS: test_load_csv_no_volume")


def test_load_dly_basic():
    """DLY binary file loads correctly with OpenInterest."""
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "ES_F.dly"
        _make_dly(fp, rows=80)
        df = load_dly(fp)

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == COLUMNS
        assert len(df) == 80
        assert df["Volume"].sum() > 0
        assert df["OpenInterest"].sum() > 0  # DLY has OI
        assert df["Open"].iloc[0] > 0
        print("  PASS: test_load_dly_basic")


def test_dly_invalid_records_skipped():
    """DLY records with date=0 or close=0 are skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "TEST.dly"
        data = bytearray()
        # Valid record
        data.extend(_DLY_STRUCT.pack(20230103, 100.0, 105.0, 95.0, 102.0, 1000, 50, 100))
        # Invalid: date=0
        data.extend(_DLY_STRUCT.pack(0, 100.0, 105.0, 95.0, 102.0, 1000, 50, 100))
        # Invalid: close=0
        data.extend(_DLY_STRUCT.pack(20230104, 100.0, 105.0, 95.0, 0.0, 1000, 50, 100))
        # Valid record
        data.extend(_DLY_STRUCT.pack(20230105, 101.0, 106.0, 96.0, 103.0, 1100, 55, 110))
        fp.write_bytes(bytes(data))

        df = load_dly(fp)
        assert len(df) == 2  # only 2 valid records
        print("  PASS: test_dly_invalid_records_skipped")


def test_ticker_from_filename():
    """Ticker extraction handles various naming patterns."""
    cases = [
        ("AAPL.csv", "AAPL"),
        ("MSFT_daily.csv", "MSFT"),
        ("GOOG, Daily.csv", "GOOG"),
        ("ES_F.dly", "ES_F"),
        ("MA.csv", "MA"),           # Mastercard — kept
        ("ma.dly", "MA"),           # lowercase Mastercard
        ("SPY-daily.csv", "SPY"),
    ]
    for filename, expected in cases:
        result = _ticker_from_filename(Path(filename))
        assert result == expected, f"Expected '{expected}' for {filename}, got '{result}'"

    # MA false positives should return empty string (moving-average exports)
    skip_cases = ["AAPL_MA_50.csv", "SPY_MA_200.csv"]
    for filename in skip_cases:
        result = _ticker_from_filename(Path(filename))
        assert result == "", f"Expected skip for {filename}, got '{result}'"

    print("  PASS: test_ticker_from_filename")


def test_load_directory_mixed():
    """Directory with mixed CSV + DLY loads and deduplicates correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # CSVs
        _make_csv(tmp / "AAPL.csv", rows=50)
        _make_csv(tmp / "MSFT.csv", rows=40)
        _make_csv(tmp / "MA.csv", rows=30)          # Mastercard
        _make_csv(tmp / "AAPL_MA_50.csv", rows=20)  # MA false positive — skipped

        # DLY
        _make_dly(tmp / "ES_F.dly", rows=100)

        # Duplicate: CSV + DLY for same ticker — DLY should win
        _make_csv(tmp / "NQ_F.csv", rows=60)
        _make_dly(tmp / "NQ_F.dly", rows=80)

        data = load_directory(tmp)

        assert "AAPL" in data
        assert "MSFT" in data
        assert "MA" in data
        assert "ES_F" in data
        assert "NQ_F" in data
        assert len(data["NQ_F"]) == 80  # DLY won

        # MA false positive should not appear as a separate ticker
        assert len(data) == 5

        print("  PASS: test_load_directory_mixed")


def test_print_summary():
    """Summary prints without errors."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _make_csv(tmp / "AAPL.csv", rows=252)
        _make_dly(tmp / "ES_F.dly", rows=252)
        data = load_directory(tmp)
        print_summary(data)
        print("  PASS: test_print_summary")


# ── Run all tests ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(" Module 1 — Data Loader Tests")
    print("=" * 50 + "\n")

    tests = [
        test_load_csv_basic,
        test_load_csv_no_volume,
        test_load_dly_basic,
        test_dly_invalid_records_skipped,
        test_ticker_from_filename,
        test_load_directory_mixed,
        test_print_summary,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'─'*50}")
    print(f" Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'─'*50}\n")
