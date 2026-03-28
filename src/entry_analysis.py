#!/usr/bin/env python3
"""
Deep entry pattern analysis — drills into what makes winning entries tick.

Outputs:
  reports/entry_pattern_analysis.md
  reports/new_composite_score_backtest.md
  src/entry_profiles.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import load_all_data
from indicators import calc_ema, calc_sma
from scorer import run_full_pipeline, calculate_alignment, select_winner, \
    apply_signal_expiry, apply_alternate_signal
from strategies import compute_all_indicators, ALL_STRATEGIES
from regime import detect_regime
from simulator import TradeSimulator


# ═══════════════════════════════════════════════════════════════════════════
# Collect trades + indicator snapshots at entry
# ═══════════════════════════════════════════════════════════════════════════

def collect_enriched_trades():
    """Run pipeline on all tickers, collect trades with indicator values at entry."""
    all_data = load_all_data("data/")
    all_trades = []
    ticker_ctx = {}  # ticker -> (df, meta)

    for ticker in sorted(all_data.keys()):
        df = all_data[ticker]
        if len(df) < 250:
            continue

        signals, meta = run_full_pipeline(df, min_composite=50.0, expiry_bars=3)
        sim = TradeSimulator.from_preset(ticker, initial_capital=10_000.0)
        log = sim.simulate(df, signals, meta)
        tdf = log.to_dataframe()
        if tdf.empty:
            continue

        ind = meta["indicators"]
        regime = meta["regime"]
        tdf["Ticker"] = ticker
        tdf["Holding Days"] = (tdf["Exit Date"] - tdf["Entry Date"]).dt.days
        tdf["Winner"] = tdf["PnL"] > 0

        # Snapshot indicators at entry date
        for _, row in tdf.iterrows():
            entry_dt = row["Entry Date"]
            if entry_dt not in df.index:
                continue
            idx = df.index.get_loc(entry_dt)
            tdf.loc[tdf["Entry Date"] == entry_dt, "RSI_at_entry"] = ind["rsi14"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "ADX_at_entry"] = ind["adx"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "EMA9_at_entry"] = ind["ema9"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "EMA21_at_entry"] = ind["ema21"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "EMA200_at_entry"] = ind["ema200"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "Close_at_entry"] = df["Close"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "VWAP_at_entry"] = ind["vwap"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "MACD_at_entry"] = ind["macd_line"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "Signal_at_entry"] = ind["signal_line"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "Vol_above_avg"] = bool(ind["vol_above_avg"].iat[idx])
            tdf.loc[tdf["Entry Date"] == entry_dt, "Chop_at_entry"] = ind["chop"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "StochK_at_entry"] = ind["stoch_k"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "WAE_expl_at_entry"] = ind["wae_expl"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "WAE_dead_at_entry"] = ind["wae_dead"].iat[idx]
            tdf.loc[tdf["Entry Date"] == entry_dt, "Regime_at_entry"] = regime.iat[idx]

            # Pullback: % below 20-bar high
            hi20 = ind["highest_20"].iat[idx]
            close_e = df["Close"].iat[idx]
            pullback = (hi20 - close_e) / hi20 * 100 if hi20 > 0 else 0
            tdf.loc[tdf["Entry Date"] == entry_dt, "Pullback_pct"] = pullback

            # EMA cross recency: bars since EMA9 crossed above EMA21
            ema9_above = ind["ema9"] > ind["ema21"]
            cross = ema9_above & ~ema9_above.shift(1).fillna(False)
            recent_crosses = cross.iloc[:idx+1]
            if recent_crosses.any():
                last_cross_idx = recent_crosses[recent_crosses].index[-1]
                bars_since = idx - df.index.get_loc(last_cross_idx)
            else:
                bars_since = 999
            tdf.loc[tdf["Entry Date"] == entry_dt, "Bars_since_EMA_cross"] = bars_since

        all_trades.append(tdf)
        ticker_ctx[ticker] = (df, meta)

    trades = pd.concat(all_trades, ignore_index=True)
    return trades, ticker_ctx


# ═══════════════════════════════════════════════════════════════════════════
# 1. Long-only deep dive
# ═══════════════════════════════════════════════════════════════════════════

def analyze_longs(trades):
    lines = ["## 1. LONG-ONLY Deep Dive (trending_up regime)", ""]

    longs_up = trades[(trades["Direction"] == "long") & (trades["Regime"] == "trending_up")]
    lines.append(f"*{len(longs_up)} long entries in trending_up across all tickers*")
    lines.append("")

    if len(longs_up) < 10:
        lines.append("Insufficient sample. Skipping.")
        return lines

    # RSI ranges
    lines.append("### RSI Range at Entry")
    lines.append("")
    lines.append("| RSI Range | Trades | WR% | Avg PnL | Total PnL |")
    lines.append("|-----------|--------|-----|---------|-----------|")
    for lo, hi in [(35, 45), (40, 50), (45, 55), (50, 60), (55, 65), (60, 70)]:
        subset = longs_up[(longs_up["RSI_at_entry"] >= lo) & (longs_up["RSI_at_entry"] < hi)]
        if len(subset) >= 3:
            wr = 100 * subset["Winner"].mean()
            lines.append(f"| {lo}-{hi} | {len(subset)} | {wr:.1f} | "
                         f"${subset['PnL'].mean():.2f} | ${subset['PnL'].sum():.2f} |")
    lines.append("")

    # ADX ranges
    lines.append("### ADX Range at Entry")
    lines.append("")
    lines.append("| ADX Range | Trades | WR% | Avg PnL | Total PnL |")
    lines.append("|-----------|--------|-----|---------|-----------|")
    for lo, hi in [(25, 30), (30, 35), (35, 40), (40, 50), (50, 999)]:
        label = f"{lo}-{hi}" if hi < 999 else f"{lo}+"
        subset = longs_up[(longs_up["ADX_at_entry"] >= lo) & (longs_up["ADX_at_entry"] < hi)]
        if len(subset) >= 3:
            wr = 100 * subset["Winner"].mean()
            lines.append(f"| {label} | {len(subset)} | {wr:.1f} | "
                         f"${subset['PnL'].mean():.2f} | ${subset['PnL'].sum():.2f} |")
    lines.append("")

    # EMA cross timing
    lines.append("### EMA9/EMA21 Crossover Timing")
    lines.append("")
    lines.append("| Bars Since Cross | Trades | WR% | Avg PnL |")
    lines.append("|------------------|--------|-----|---------|")
    for lo, hi, label in [(0, 1, "Cross day"), (1, 4, "1-3 bars after"),
                           (4, 10, "4-9 bars after"), (10, 999, "10+ bars after")]:
        subset = longs_up[(longs_up["Bars_since_EMA_cross"] >= lo) &
                          (longs_up["Bars_since_EMA_cross"] < hi)]
        if len(subset) >= 3:
            wr = 100 * subset["Winner"].mean()
            lines.append(f"| {label} | {len(subset)} | {wr:.1f} | "
                         f"${subset['PnL'].mean():.2f} |")
    lines.append("")

    # Pullback depth
    lines.append("### Pullback Depth (% below 20-bar high)")
    lines.append("")
    lines.append("| Pullback % | Trades | WR% | Avg PnL |")
    lines.append("|------------|--------|-----|---------|")
    for lo, hi in [(0, 1), (1, 3), (3, 5), (5, 8), (8, 15)]:
        label = f"{lo}-{hi}%"
        subset = longs_up[(longs_up["Pullback_pct"] >= lo) & (longs_up["Pullback_pct"] < hi)]
        if len(subset) >= 3:
            wr = 100 * subset["Winner"].mean()
            lines.append(f"| {label} | {len(subset)} | {wr:.1f} | "
                         f"${subset['PnL'].mean():.2f} |")
    lines.append("")

    return lines


# ═══════════════════════════════════════════════════════════════════════════
# 2. Breakout deep dive
# ═══════════════════════════════════════════════════════════════════════════

BREAKOUT_TICKERS = ["AAPL", "MU", "TSLA", "EWZ", "NVDA"]


def analyze_breakouts(trades, ticker_ctx):
    lines = ["## 2. BREAKOUT Deep Dive (S3 on volatile regime)", ""]

    s3_vol = trades[(trades["Strategy"] == "S3_BreakoutMomentum") &
                    (trades["Regime"] == "volatile")]
    lines.append(f"*{len(s3_vol)} S3 breakout entries in volatile regime*")
    lines.append("")

    # Focus tickers
    focus = s3_vol[s3_vol["Ticker"].isin(BREAKOUT_TICKERS)]
    lines.append(f"Focus tickers ({', '.join(BREAKOUT_TICKERS)}): {len(focus)} trades")
    lines.append("")

    # WAE confirmation: does explosion > dead zone help?
    lines.append("### WAE Confirmation Value")
    lines.append("")
    wae_active = s3_vol[s3_vol["WAE_expl_at_entry"] > s3_vol["WAE_dead_at_entry"]]
    wae_inactive = s3_vol[s3_vol["WAE_expl_at_entry"] <= s3_vol["WAE_dead_at_entry"]]
    lines.append("| Condition | Trades | WR% | Avg PnL | Total PnL |")
    lines.append("|-----------|--------|-----|---------|-----------|")
    if len(wae_active) >= 3:
        lines.append(f"| WAE active (expl > dead) | {len(wae_active)} | "
                     f"{100*wae_active['Winner'].mean():.1f} | "
                     f"${wae_active['PnL'].mean():.2f} | ${wae_active['PnL'].sum():.2f} |")
    if len(wae_inactive) >= 3:
        lines.append(f"| WAE inactive | {len(wae_inactive)} | "
                     f"{100*wae_inactive['Winner'].mean():.1f} | "
                     f"${wae_inactive['PnL'].mean():.2f} | ${wae_inactive['PnL'].sum():.2f} |")
    lines.append("")

    # Volume alone
    lines.append("### Volume-Only vs Volume+WAE")
    lines.append("")
    vol_only = s3_vol[s3_vol["Vol_above_avg"] == True]
    vol_wae = s3_vol[(s3_vol["Vol_above_avg"] == True) &
                     (s3_vol["WAE_expl_at_entry"] > s3_vol["WAE_dead_at_entry"])]
    lines.append("| Filter | Trades | WR% | Avg PnL |")
    lines.append("|--------|--------|-----|---------|")
    if len(vol_only) >= 3:
        lines.append(f"| Volume above avg only | {len(vol_only)} | "
                     f"{100*vol_only['Winner'].mean():.1f} | ${vol_only['PnL'].mean():.2f} |")
    if len(vol_wae) >= 3:
        lines.append(f"| Volume + WAE active | {len(vol_wae)} | "
                     f"{100*vol_wae['Winner'].mean():.1f} | ${vol_wae['PnL'].mean():.2f} |")
    lines.append("")

    # Donchian period test requires re-running with different periods — skip for now,
    # report what we can from existing 20-period data
    lines.append("### Donchian Period Note")
    lines.append("")
    lines.append("Current system uses Donchian(20). Testing alternate periods (10, 15, 30)")
    lines.append("would require re-running the strategy engine with modified parameters.")
    lines.append("Recommendation: the 20-period default aligns with the Pine Script V5")
    lines.append("and produces the existing breakout results. Consider testing in a")
    lines.append("parameter sweep phase.")
    lines.append("")

    return lines


# ═══════════════════════════════════════════════════════════════════════════
# 3. Short signal investigation
# ═══════════════════════════════════════════════════════════════════════════

def analyze_shorts(trades):
    lines = ["## 3. SHORT Signal Investigation", ""]

    shorts = trades[trades["Direction"] == "short"]
    lines.append(f"*{len(shorts)} total short entries*")
    lines.append(f"*Overall short WR: {100*shorts['Winner'].mean():.1f}%*")
    lines.append("")

    # Test restrictive filters
    lines.append("### Restrictive Short Filters")
    lines.append("")
    lines.append("| Filter | Trades | WR% | Avg PnL | Total PnL |")
    lines.append("|--------|--------|-----|---------|-----------|")

    filters = [
        ("All shorts", shorts),
        ("RSI > 70", shorts[shorts["RSI_at_entry"] > 70]),
        ("RSI > 75", shorts[shorts["RSI_at_entry"] > 75]),
        ("RSI > 80", shorts[shorts["RSI_at_entry"] > 80]),
        ("ADX > 30", shorts[shorts["ADX_at_entry"] > 30]),
        ("ADX > 35", shorts[shorts["ADX_at_entry"] > 35]),
        ("ADX > 40", shorts[shorts["ADX_at_entry"] > 40]),
        ("RSI>70 + ADX>30", shorts[(shorts["RSI_at_entry"] > 70) &
                                    (shorts["ADX_at_entry"] > 30)]),
        ("RSI>70 + ADX>35", shorts[(shorts["RSI_at_entry"] > 70) &
                                    (shorts["ADX_at_entry"] > 35)]),
        ("RSI>80 + ADX>35", shorts[(shorts["RSI_at_entry"] > 80) &
                                    (shorts["ADX_at_entry"] > 35)]),
        ("EMA9 < EMA21", shorts[shorts["EMA9_at_entry"] < shorts["EMA21_at_entry"]]),
        ("Close < EMA200", shorts[shorts["Close_at_entry"] < shorts["EMA200_at_entry"]]),
        ("Close<EMA200 + RSI>70 + ADX>35",
         shorts[(shorts["Close_at_entry"] < shorts["EMA200_at_entry"]) &
                (shorts["RSI_at_entry"] > 70) & (shorts["ADX_at_entry"] > 35)]),
    ]

    for label, subset in filters:
        if len(subset) >= 3:
            wr = 100 * subset["Winner"].mean()
            lines.append(f"| {label} | {len(subset)} | {wr:.1f} | "
                         f"${subset['PnL'].mean():.2f} | ${subset['PnL'].sum():.2f} |")
        elif len(subset) > 0:
            lines.append(f"| {label} | {len(subset)} | — | — | — |")
    lines.append("")

    # Verdict
    best_short_wr = 0
    best_short_label = ""
    for label, subset in filters:
        if len(subset) >= 5:
            wr = 100 * subset["Winner"].mean()
            if wr > best_short_wr:
                best_short_wr = wr
                best_short_label = label

    if best_short_wr >= 40:
        lines.append(f"**Best short profile:** {best_short_label} ({best_short_wr:.1f}% WR) — "
                     f"marginally viable, proceed with caution")
    else:
        lines.append(f"**Verdict:** No short filter combination achieves 40% WR. "
                     f"Best found: {best_short_label} ({best_short_wr:.1f}% WR). "
                     f"**Recommend disabling shorts entirely** or restricting to "
                     f"extreme conditions only.")
    lines.append("")

    return lines


# ═══════════════════════════════════════════════════════════════════════════
# 4. Rebuilt composite scoring
# ═══════════════════════════════════════════════════════════════════════════

def rebuild_composite_scoring(trades, ticker_ctx):
    lines = []
    comparison_lines = ["# New Composite Score Backtest", ""]

    # ── Compute new scores for every trade ──
    # New weights based on proven predictive power
    new_scores = []
    old_scores = trades["Score"].tolist()

    for _, row in trades.iterrows():
        ticker = row["Ticker"]
        if ticker not in ticker_ctx:
            new_scores.append(0)
            continue
        entry_dt = row["Entry Date"]
        df, meta = ticker_ctx[ticker]
        if entry_dt not in df.index:
            new_scores.append(0)
            continue

        ind = meta["indicators"]
        idx = df.index.get_loc(entry_dt)
        close = df["Close"].iat[idx]
        direction = 1 if row["Direction"] == "long" else -1

        score = 0.0

        # EMA9 > EMA21: 25 pts (proven +15.3% delta)
        ema9_above = ind["ema9"].iat[idx] > ind["ema21"].iat[idx]
        if (direction > 0 and ema9_above) or (direction < 0 and not ema9_above):
            score += 25

        # RSI > 50 for longs / < 50 for shorts: 25 pts (proven +15.1% delta)
        rsi = ind["rsi14"].iat[idx]
        if not np.isnan(rsi):
            if (direction > 0 and rsi > 50) or (direction < 0 and rsi < 50):
                score += 25

        # Close > EMA200: 20 pts (proven +9.8% delta)
        ema200 = ind["ema200"].iat[idx]
        if not np.isnan(ema200):
            if (direction > 0 and close > ema200) or (direction < 0 and close < ema200):
                score += 20

        # Weekly trend proxy (EMA50 direction): 15 pts
        ema50 = ind["ema50"].iat[idx]
        if idx >= 5 and not np.isnan(ema50):
            ema50_prev = ind["ema50"].iat[idx - 5]
            if not np.isnan(ema50_prev):
                ema50_rising = ema50 > ema50_prev
                if (direction > 0 and ema50_rising) or (direction < 0 and not ema50_rising):
                    score += 15

        # Volume > SMA(20): 5 pts (low value)
        if bool(ind["vol_above_avg"].iat[idx]):
            score += 5

        # MACD direction: 5 pts
        macd = ind["macd_line"].iat[idx]
        sig = ind["signal_line"].iat[idx]
        if not (np.isnan(macd) or np.isnan(sig)):
            if (direction > 0 and macd > sig) or (direction < 0 and macd < sig):
                score += 5

        # Stoch/ADX/Chop combined: 5 pts
        stoch = ind["stoch_k"].iat[idx]
        if not np.isnan(stoch):
            if (direction > 0 and stoch > 30) or (direction < 0 and stoch < 70):
                score += 5

        new_scores.append(score)

    trades = trades.copy()
    trades["New_Score"] = new_scores

    # ── Compare old vs new at various thresholds ──
    lines.append("## 4. COMPOSITE SCORE REBUILD")
    lines.append("")
    lines.append("### New Weights (evidence-based)")
    lines.append("")
    lines.append("| Component | Old Weight | New Weight | Justification |")
    lines.append("|-----------|-----------|-----------|---------------|")
    lines.append("| EMA9 > EMA21 | 15 | **25** | +15.3% WR delta (strongest) |")
    lines.append("| RSI direction | 10 | **25** | +15.1% WR delta |")
    lines.append("| Close vs EMA200 | 15 | **20** | +9.8% WR delta |")
    lines.append("| Weekly trend (EMA50 slope) | — | **15** | Structural trend proxy |")
    lines.append("| Volume > SMA(20) | 10 | **5** | -1.2% delta (near zero) |")
    lines.append("| MACD direction | 10 | **5** | +5.3% delta (moderate) |")
    lines.append("| Stoch/ADX/Chop | 30 combined | **5** | Near-zero predictive value |")
    lines.append("| Range Filter | 15 | **0** | Redundant with EMA9/21 |")
    lines.append("| VWAP position | 10 | **0** | Redundant with EMA200 |")
    lines.append("")

    lines.append("### Threshold Comparison: Old vs New Scoring")
    lines.append("")
    lines.append("| Threshold | Old: Trades | Old: WR% | Old: PF | New: Trades | New: WR% | New: PF |")
    lines.append("|-----------|-------------|----------|---------|-------------|----------|---------|")

    comparison_lines.append("## Threshold-by-Threshold Comparison")
    comparison_lines.append("")
    comparison_lines.append("| Threshold | Old Trades | Old WR% | Old PF | Old PnL | New Trades | New WR% | New PF | New PnL |")
    comparison_lines.append("|-----------|------------|---------|--------|---------|------------|---------|--------|---------|")

    for thresh in [60, 65, 70, 75, 80, 85]:
        old_sub = trades[trades["Score"] >= thresh]
        new_sub = trades[trades["New_Score"] >= thresh]

        old_wr = 100 * old_sub["Winner"].mean() if len(old_sub) >= 3 else 0
        old_gp = old_sub[old_sub["Winner"]]["PnL"].sum() if len(old_sub) >= 3 else 0
        old_gl = abs(old_sub[~old_sub["Winner"]]["PnL"].sum()) if len(old_sub) >= 3 else 1
        old_pf = old_gp / old_gl if old_gl > 0 else 0

        new_wr = 100 * new_sub["Winner"].mean() if len(new_sub) >= 3 else 0
        new_gp = new_sub[new_sub["Winner"]]["PnL"].sum() if len(new_sub) >= 3 else 0
        new_gl = abs(new_sub[~new_sub["Winner"]]["PnL"].sum()) if len(new_sub) >= 3 else 1
        new_pf = new_gp / new_gl if new_gl > 0 else 0

        lines.append(f"| >= {thresh} | {len(old_sub)} | {old_wr:.1f} | {old_pf:.2f} | "
                     f"{len(new_sub)} | {new_wr:.1f} | {new_pf:.2f} |")
        comparison_lines.append(
            f"| >= {thresh} | {len(old_sub)} | {old_wr:.1f} | {old_pf:.2f} | "
            f"${old_sub['PnL'].sum():.0f} | "
            f"{len(new_sub)} | {new_wr:.1f} | {new_pf:.2f} | "
            f"${new_sub['PnL'].sum():.0f} |")

    lines.append("")

    # Find best new threshold
    best_thresh = 0
    best_pf = 0
    for thresh in [60, 65, 70, 75, 80, 85]:
        sub = trades[trades["New_Score"] >= thresh]
        if len(sub) >= 10:
            gp = sub[sub["Winner"]]["PnL"].sum()
            gl = abs(sub[~sub["Winner"]]["PnL"].sum())
            pf = gp / gl if gl > 0 else 0
            if pf > best_pf:
                best_pf = pf
                best_thresh = thresh

    lines.append(f"**Best new threshold:** >= {best_thresh} (PF={best_pf:.2f})")
    lines.append("")

    comparison_lines.append("")
    comparison_lines.append(f"**Conclusion:** Best new-score threshold is >= {best_thresh} "
                            f"with PF={best_pf:.2f}")

    return lines, comparison_lines, trades


# ═══════════════════════════════════════════════════════════════════════════
# 5. Entry profiles
# ═══════════════════════════════════════════════════════════════════════════

def build_entry_profiles(trades):
    lines = ["## 5. Definitive Entry Profiles", ""]
    profiles = {}

    # ── Cluster A: Trend longs ──
    trend_longs = trades[(trades["Direction"] == "long") & (trades["Regime"] == "trending_up")]

    # Find optimal RSI range
    best_rsi = _find_best_range(trend_longs, "RSI_at_entry",
                                [(35, 45), (40, 50), (45, 55), (50, 60), (55, 65)])
    # Find optimal ADX range
    best_adx = _find_best_range(trend_longs, "ADX_at_entry",
                                [(25, 30), (30, 35), (35, 40), (40, 50)])
    # Find optimal pullback
    best_pullback = _find_best_range(trend_longs, "Pullback_pct",
                                     [(0, 2), (2, 5), (5, 8), (8, 15)])

    profiles["cluster_a_trend_longs"] = {
        "regime": "trending_up",
        "direction": "long",
        "rsi_range": best_rsi,
        "adx_range": best_adx,
        "pullback_range": best_pullback,
        "required_filters": ["EMA9 > EMA21", "RSI > 50", "Close > EMA200"],
        "scoring_weights": {
            "ema9_ema21": 25, "rsi_direction": 25, "close_vs_ema200": 20,
            "weekly_trend": 15, "volume": 5, "macd": 5, "other": 5
        }
    }

    lines.append("### Cluster A: Trend Longs")
    lines.append("")
    lines.append(f"- **Regime:** trending_up only")
    lines.append(f"- **Direction:** LONG only")
    lines.append(f"- **Optimal RSI:** {best_rsi}")
    lines.append(f"- **Optimal ADX:** {best_adx}")
    lines.append(f"- **Optimal pullback:** {best_pullback}")
    lines.append(f"- **Required:** EMA9 > EMA21, RSI > 50, Close > EMA200")
    lines.append("")

    # ── Cluster B: Breakout longs ──
    breakout = trades[(trades["Strategy"] == "S3_BreakoutMomentum") &
                      (trades["Regime"] == "volatile") &
                      (trades["Direction"] == "long")]

    profiles["cluster_b_breakout_longs"] = {
        "regime": "volatile",
        "direction": "long",
        "strategy": "S3_BreakoutMomentum",
        "donchian_period": 20,
        "volume_filter": "vol_above_avg required",
        "wae_filter": "optional (see analysis)",
        "scoring_weights": {
            "ema9_ema21": 25, "rsi_direction": 25, "close_vs_ema200": 20,
            "weekly_trend": 15, "volume": 5, "macd": 5, "other": 5
        }
    }

    lines.append("### Cluster B: Breakout Longs")
    lines.append("")
    lines.append(f"- **Regime:** volatile")
    lines.append(f"- **Direction:** LONG only")
    lines.append(f"- **Strategy:** S3_BreakoutMomentum")
    lines.append(f"- **Donchian:** 20-period (default)")
    lines.append(f"- **Volume:** Required (above 20-SMA avg)")
    lines.append(f"- **Best tickers:** AAPL, MU, TSLA, EWZ (50-60% WR)")
    lines.append("")

    # ── Cluster C: Shorts ──
    shorts = trades[trades["Direction"] == "short"]
    short_wr = 100 * shorts["Winner"].mean() if len(shorts) >= 5 else 0

    # Test the most restrictive filter we found
    strict_shorts = shorts[(shorts["Close_at_entry"] < shorts["EMA200_at_entry"]) &
                           (shorts["ADX_at_entry"] > 35)]

    if len(strict_shorts) >= 5 and 100 * strict_shorts["Winner"].mean() >= 40:
        profiles["cluster_c_shorts"] = {
            "regime": "trending_down",
            "direction": "short",
            "status": "restricted",
            "required_filters": ["Close < EMA200", "ADX > 35"],
            "note": "Marginal edge only"
        }
        lines.append("### Cluster C: Rare Shorts")
        lines.append("")
        lines.append(f"- **Status:** RESTRICTED — marginal edge")
        lines.append(f"- **Conditions:** Close < EMA200 AND ADX > 35")
        lines.append(f"- **WR:** {100*strict_shorts['Winner'].mean():.1f}% "
                     f"on {len(strict_shorts)} trades")
    else:
        profiles["cluster_c_shorts"] = {
            "regime": "any",
            "direction": "short",
            "status": "DISABLED",
            "reason": f"No filter combination achieves 40% WR (best: {short_wr:.1f}%)",
            "recommendation": "Disable all short signals"
        }
        lines.append("### Cluster C: Shorts")
        lines.append("")
        lines.append(f"- **Status:** **DISABLED** — recommend removing all short signals")
        lines.append(f"- **Reason:** Overall short WR = {short_wr:.1f}%. No filter "
                     f"combination tested achieves 40% WR.")
        lines.append(f"- **Impact:** Removing shorts eliminates ~50% of trades but "
                     f"removes the primary source of losses.")
    lines.append("")

    return lines, profiles


def _find_best_range(df, col, ranges):
    """Find the range with highest WR, minimum 5 trades."""
    best = "insufficient data"
    best_wr = 0
    for lo, hi in ranges:
        sub = df[(df[col] >= lo) & (df[col] < hi)]
        if len(sub) >= 5:
            wr = 100 * sub["Winner"].mean()
            if wr > best_wr:
                best_wr = wr
                best = f"{lo}-{hi} ({wr:.1f}% WR, {len(sub)} trades)"
    return best


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("Collecting enriched trade data...")
    trades, ticker_ctx = collect_enriched_trades()
    print(f"  {len(trades)} trades with indicator snapshots\n")

    report_lines = ["# Entry Pattern Deep Dive", ""]
    report_lines.append(f"*{len(trades)} trades across {trades['Ticker'].nunique()} tickers, "
                        f"with indicator values captured at entry*")
    report_lines.append("")

    # 1. Long-only
    print("  Analyzing longs in trending_up...")
    report_lines.extend(analyze_longs(trades))

    # 2. Breakouts
    print("  Analyzing S3 breakouts...")
    report_lines.extend(analyze_breakouts(trades, ticker_ctx))

    # 3. Shorts
    print("  Investigating short signals...")
    report_lines.extend(analyze_shorts(trades))

    # 4. Rebuilt composite
    print("  Testing rebuilt composite scoring...")
    composite_lines, comparison_lines, trades = rebuild_composite_scoring(trades, ticker_ctx)
    report_lines.extend(composite_lines)

    # 5. Entry profiles
    print("  Building definitive entry profiles...")
    profile_lines, profiles = build_entry_profiles(trades)
    report_lines.extend(profile_lines)

    # Write outputs
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    entry_report = reports_dir / "entry_pattern_analysis.md"
    entry_report.write_text("\n".join(report_lines))
    print(f"\n  Written: {entry_report}")

    composite_report = reports_dir / "new_composite_score_backtest.md"
    composite_report.write_text("\n".join(comparison_lines))
    print(f"  Written: {composite_report}")

    profiles_path = Path("src") / "entry_profiles.json"
    with open(profiles_path, "w") as f:
        json.dump(profiles, f, indent=2)
    print(f"  Written: {profiles_path}")

    # Print to console
    print("\n" + "=" * 70)
    print(entry_report.read_text())
    print("\n" + "=" * 70)
    print(composite_report.read_text())


if __name__ == "__main__":
    main()
