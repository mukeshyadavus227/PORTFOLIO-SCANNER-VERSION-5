"""
Market regime detection based on ADX, Choppiness Index, and ATR filters.

Classifies each bar into one of:
  trending_up, trending_down, ranging, volatile, undefined
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from tabulate import tabulate


# ═══════════════════════════════════════════════════════════════════════════
# 1. Compute required indicators
# ═══════════════════════════════════════════════════════════════════════════

def _compute_indicators(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Calculate all indicators needed for regime detection."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from indicators import calc_adx, calc_atr, calc_choppiness_index, calc_ema, calc_sma

    plus_di, minus_di, adx = calc_adx(df, 14, 14)
    atr = calc_atr(df, 14)
    atr_sma20 = calc_sma(atr, 20)
    chop = calc_choppiness_index(df, 14)
    ema200 = calc_ema(df["Close"], 200)

    return {
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "atr": atr,
        "atr_sma20": atr_sma20,
        "chop": chop,
        "ema200": ema200,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. Regime detection
# ═══════════════════════════════════════════════════════════════════════════

REGIMES = ["trending_up", "trending_down", "ranging", "volatile", "undefined"]


def detect_regime(df: pd.DataFrame,
                  indicators: dict[str, pd.Series] | None = None) -> pd.Series:
    """Classify each bar into a market regime.

    Rules (evaluated in priority order):
      trending_up:   ADX > 25  AND  +DI > -DI  AND  close > EMA(200)
      trending_down: ADX > 25  AND  -DI > +DI  AND  close < EMA(200)
      ranging:       ADX < 20  AND  Choppiness > 61.8
      volatile:      ADX 20-25  OR  ATR > 1.5 * SMA(ATR, 20)
      undefined:     everything else
    """
    if indicators is None:
        indicators = _compute_indicators(df)

    adx = indicators["adx"]
    plus_di = indicators["plus_di"]
    minus_di = indicators["minus_di"]
    atr = indicators["atr"]
    atr_sma20 = indicators["atr_sma20"]
    chop = indicators["chop"]
    ema200 = indicators["ema200"]
    close = df["Close"]

    regime = pd.Series("undefined", index=df.index, dtype="object")

    # Trending up
    mask_up = (adx > 25) & (plus_di > minus_di) & (close > ema200)
    regime[mask_up] = "trending_up"

    # Trending down
    mask_down = (adx > 25) & (minus_di > plus_di) & (close < ema200)
    regime[mask_down] = "trending_down"

    # Ranging (only where not already trending)
    already = mask_up | mask_down
    mask_range = ~already & (adx < 20) & (chop > 61.8)
    regime[mask_range] = "ranging"

    # Volatile (only where not already classified)
    already = already | mask_range
    atr_spike = atr > 1.5 * atr_sma20
    mask_vol = ~already & ((adx >= 20) & (adx <= 25) | atr_spike)
    regime[mask_vol] = "volatile"

    return regime


# ═══════════════════════════════════════════════════════════════════════════
# 3. Regime summary
# ═══════════════════════════════════════════════════════════════════════════

def regime_summary(regimes: pd.Series) -> dict:
    """Compute counts, durations, and transition matrix for regimes.

    Returns dict with keys: counts, avg_duration, transitions.
    """
    total = len(regimes)
    valid = regimes.dropna()

    # ── Counts & percentages ──
    counts = {}
    for r in REGIMES:
        n = (valid == r).sum()
        counts[r] = {"bars": int(n), "pct": round(100 * n / total, 1) if total else 0.0}

    # ── Average consecutive duration ──
    avg_duration = {}
    shifted = valid != valid.shift(1)
    group_ids = shifted.cumsum()
    for r in REGIMES:
        mask = valid == r
        if not mask.any():
            avg_duration[r] = 0.0
            continue
        run_lengths = mask.groupby(group_ids).sum()
        run_lengths = run_lengths[run_lengths > 0]
        avg_duration[r] = round(float(run_lengths.mean()), 1) if len(run_lengths) else 0.0

    # ── Transition matrix ──
    transitions = {r: {s: 0 for s in REGIMES} for r in REGIMES}
    prev = valid.values[:-1]
    curr = valid.values[1:]
    for p, c in zip(prev, curr):
        if p != c:
            transitions[p][c] += 1

    return {
        "counts": counts,
        "avg_duration": avg_duration,
        "transitions": transitions,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Plot
# ═══════════════════════════════════════════════════════════════════════════

REGIME_COLORS = {
    "trending_up": "#2ecc71",
    "trending_down": "#e74c3c",
    "ranging": "#3498db",
    "volatile": "#f39c12",
    "undefined": "#bdc3c7",
}


def plot_regimes(df: pd.DataFrame, regimes: pd.Series, ticker: str,
                 out_dir: str | Path = "output") -> Path:
    """Save a price chart with colored regime background bands."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(18, 6))
    ax.plot(df.index, df["Close"], color="black", linewidth=0.6, label="Close")

    # Paint regime backgrounds
    dates = df.index
    for i in range(len(dates)):
        color = REGIME_COLORS.get(regimes.iloc[i], "#bdc3c7")
        ax.axvspan(
            dates[i] - pd.Timedelta(hours=12),
            dates[i] + pd.Timedelta(hours=12),
            alpha=0.25, color=color, linewidth=0,
        )

    # Legend
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=c, alpha=0.4, label=r) for r, c in REGIME_COLORS.items()]
    ax.legend(handles=handles, loc="upper left", fontsize=8, ncol=5)

    ax.set_title(f"{ticker} — Market Regimes", fontsize=14)
    ax.set_ylabel("Price")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    fig.autofmt_xdate()
    fig.tight_layout()

    filepath = out_dir / f"{ticker}_regimes.png"
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    return filepath


# ═══════════════════════════════════════════════════════════════════════════
# 5. Pretty-print helpers
# ═══════════════════════════════════════════════════════════════════════════

def print_regime_summary(ticker: str, summary: dict) -> None:
    """Print formatted regime summary for a ticker."""
    print(f"\n{'=' * 60}")
    print(f"  REGIME SUMMARY — {ticker}")
    print(f"{'=' * 60}")

    # Counts table
    rows = []
    for r in REGIMES:
        c = summary["counts"][r]
        dur = summary["avg_duration"][r]
        rows.append({
            "Regime": r,
            "Bars": c["bars"],
            "%": c["pct"],
            "Avg Run": dur,
        })
    print(tabulate(rows, headers="keys", tablefmt="simple", floatfmt=".1f"))

    # Transition matrix
    print(f"\nTransition matrix (from → to):")
    labels = ["trend_up", "trend_dn", "ranging", "volatile", "undef"]
    header = f"{'':>12s}  " + "  ".join(f"{l:>9s}" for l in labels)
    print(header)
    for r, short in zip(REGIMES, labels):
        vals = [summary["transitions"][r][s] for s in REGIMES]
        row_str = "  ".join(f"{v:>9d}" for v in vals)
        print(f"{short:>12s}  {row_str}")


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from data_loader import load_sierra_dly

    tickers = [
        ("SPY", "data/SPY.dly"),
        ("CL", "data/CL.dly"),
    ]

    for ticker, path in tickers:
        df = load_sierra_dly(path)
        indicators = _compute_indicators(df)
        regimes = detect_regime(df, indicators)

        summary = regime_summary(regimes)
        print_regime_summary(ticker, summary)

        # Spot-check: 2020 crash (Feb-Mar 2020) should be trending_down
        crash_window = regimes.loc["2020-02-20":"2020-03-23"]
        if len(crash_window):
            down_pct = (crash_window == "trending_down").mean() * 100
            vol_pct = (crash_window == "volatile").mean() * 100
            print(f"\n  Spot-check 2020 crash (Feb 20 – Mar 23):")
            print(f"    trending_down: {down_pct:.0f}%  volatile: {vol_pct:.0f}%")

        # Spot-check: 2023-24 bull run should be trending_up
        bull_window = regimes.loc["2023-06-01":"2024-06-01"]
        if len(bull_window):
            up_pct = (bull_window == "trending_up").mean() * 100
            print(f"  Spot-check 2023-24 bull ({ticker}):")
            print(f"    trending_up: {up_pct:.0f}%")

        # Save plot
        png = plot_regimes(df, regimes, ticker)
        print(f"\n  Chart saved: {png}")
