#!/usr/bin/env python3
"""
V6 Mode A Gate Diagnostic for SPY.

Computes all V6 indicators on SPY data and checks each Mode A condition
individually, in pairs, and combined over the last 500 bars to identify
which condition(s) are the bottleneck.
"""

import sys
from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicators import calc_ema, calc_rsi, calc_adx, calc_atr, calc_macd, calc_sma

# V6 parameters (matching validate_pinescript.py)
V6 = {
    "ema_fast": 9,
    "ema_slow": 50,
    "ema_trend": 200,
    "rsi_lo_entry": 55,
    "rsi_hi_entry": 80,
    "pullback_pct": 1.0,
    "adx_trend_thr": 30,
}


def compute_weekly_indicators(df: pd.DataFrame) -> pd.DataFrame:
    weekly = df.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()
    wk_ema9 = calc_ema(weekly["Close"], 9)
    wk_ema21 = calc_ema(weekly["Close"], 21)
    wk_ema200 = calc_ema(weekly["Close"], 200)
    wk_data = pd.DataFrame({
        "wk_ema9": wk_ema9,
        "wk_ema21": wk_ema21,
        "wk_ema200": wk_ema200,
        "wk_close": weekly["Close"],
    })
    return wk_data.reindex(df.index, method="ffill")


def main():
    # Load data
    data_path = Path(__file__).resolve().parent.parent / "data" / "SPY.dly"
    df = load_sierra_dly(str(data_path))
    print(f"Loaded SPY: {len(df)} total bars, date range {df.index[0].date()} to {df.index[-1].date()}")

    close = df["Close"]

    # Compute indicators
    ema9 = calc_ema(close, V6["ema_fast"])
    ema50 = calc_ema(close, V6["ema_slow"])
    ema200 = calc_ema(close, V6["ema_trend"])
    rsi = calc_rsi(close, 14)
    plus_di, minus_di, adx = calc_adx(df, 14, 14)
    atr = calc_atr(df, 14)
    macd_line, signal_line, histogram = calc_macd(close, 12, 26, 9)
    vol_sma20 = calc_sma(df["Volume"], 20)
    high20 = df["High"].rolling(20).max()

    # Weekly
    wk = compute_weekly_indicators(df)
    wk_bullish = (wk["wk_ema9"] > wk["wk_ema21"]) & (wk["wk_close"] > wk["wk_ema200"])
    wk_bullish = wk_bullish.fillna(False)

    # Take last 500 bars
    N = 500
    sl = slice(-N, None)
    c = close.iloc[sl]
    dates = df.index[sl]

    # Compute pct_from_high
    h20 = high20.iloc[sl]
    pct_from_hi = (h20 - c) / h20 * 100

    # Build boolean masks for each condition
    conds = {}
    conds["EMA9 > EMA50"] = (ema9.iloc[sl] > ema50.iloc[sl]).values
    conds["RSI 55-80"] = ((rsi.iloc[sl] >= V6["rsi_lo_entry"]) & (rsi.iloc[sl] <= V6["rsi_hi_entry"])).values
    conds["Near 20-bar High (<=1%)"] = (pct_from_hi <= V6["pullback_pct"]).values
    conds["Close > EMA200"] = (c > ema200.iloc[sl]).values
    conds["ADX > 30"] = (adx.iloc[sl] > V6["adx_trend_thr"]).values
    conds["Volume > volSMA*0.8"] = (df["Volume"].iloc[sl] > vol_sma20.iloc[sl] * 0.8).values
    conds["Regime=trending_up"] = (
        (adx.iloc[sl] > V6["adx_trend_thr"]) &
        (plus_di.iloc[sl] > minus_di.iloc[sl]) &
        (c > ema200.iloc[sl])
    ).values
    conds["Weekly Bullish"] = wk_bullish.iloc[sl].values

    # Replace NaN-derived False with actual False (NaN comparisons are False already)
    for k in conds:
        conds[k] = np.nan_to_num(conds[k], nan=0).astype(bool)

    # ── Individual conditions ──
    print(f"\n{'='*65}")
    print(f"  V6 MODE A GATE DIAGNOSTIC — SPY last {N} bars")
    print(f"  Date range: {dates[0].date()} to {dates[-1].date()}")
    print(f"{'='*65}\n")

    print(f"{'Condition':<28} {'Pass':>6} {'Rate %':>8}")
    print(f"{'-'*28} {'-'*6} {'-'*8}")
    for name, mask in conds.items():
        cnt = mask.sum()
        pct = 100 * cnt / N
        print(f"{name:<28} {cnt:>6} {pct:>7.1f}%")

    # ── Combined gate (all 8) ──
    all_pass = np.ones(N, dtype=bool)
    for mask in conds.values():
        all_pass &= mask
    combined_cnt = all_pass.sum()
    combined_pct = 100 * combined_cnt / N
    print(f"\n{'COMBINED (all 8)':<28} {combined_cnt:>6} {combined_pct:>7.1f}%")

    # ── Pairwise intersections ──
    print(f"\n{'='*65}")
    print(f"  PAIRWISE INTERSECTIONS (sorted by most restrictive)")
    print(f"{'='*65}\n")

    pairs = []
    names = list(conds.keys())
    for i, j in combinations(range(len(names)), 2):
        n1, n2 = names[i], names[j]
        both = conds[n1] & conds[n2]
        cnt = both.sum()
        pct = 100 * cnt / N
        pairs.append((cnt, pct, n1, n2))

    pairs.sort(key=lambda x: x[0])

    print(f"{'Condition A':<28} {'Condition B':<28} {'Pass':>6} {'Rate %':>8}")
    print(f"{'-'*28} {'-'*28} {'-'*6} {'-'*8}")
    for cnt, pct, n1, n2 in pairs[:15]:
        print(f"{n1:<28} {n2:<28} {cnt:>6} {pct:>7.1f}%")

    # ── Cumulative cascade ──
    print(f"\n{'='*65}")
    print(f"  CUMULATIVE CASCADE (adding conditions one by one)")
    print(f"{'='*65}\n")

    # Order by individual pass rate (most permissive first) to show where drop happens
    ordered = sorted(conds.items(), key=lambda x: x[1].sum(), reverse=True)
    running = np.ones(N, dtype=bool)
    print(f"{'+ Condition':<28} {'Remaining':>10} {'Rate %':>8} {'Drop':>8}")
    print(f"{'-'*28} {'-'*10} {'-'*8} {'-'*8}")
    prev = N
    for name, mask in ordered:
        running &= mask
        cnt = running.sum()
        pct = 100 * cnt / N
        drop = prev - cnt
        print(f"{name:<28} {cnt:>10} {pct:>7.1f}% {drop:>7}")
        prev = cnt

    # ── Recent bars detail ──
    print(f"\n{'='*65}")
    print(f"  LAST 20 BARS — per-condition pass/fail")
    print(f"{'='*65}\n")

    short_names = ["EMA", "RSI", "Hi20", ">200", "ADX", "Vol", "Rgme", "Wkly"]
    header = f"{'Date':<12} " + " ".join(f"{s:>5}" for s in short_names) + "  ALL"
    print(header)
    print("-" * len(header))
    for idx in range(-20, 0):
        bar_idx = N + idx  # index into the sliced arrays
        d = dates[bar_idx].strftime("%Y-%m-%d")
        vals = []
        for name in conds:
            vals.append("  YES" if conds[name][bar_idx] else "   no")
        all_ok = "  YES" if all_pass[bar_idx] else "   no"
        print(f"{d:<12} " + " ".join(vals) + f"  {all_ok}")

    print()


if __name__ == "__main__":
    main()
