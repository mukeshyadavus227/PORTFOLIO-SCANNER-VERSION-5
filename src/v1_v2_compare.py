#!/usr/bin/env python3
"""
V1 vs V2 signal frequency comparison across all 15 tickers.

V1: Pure daily-calibrated conditions (includes EMA21 touch requirement)
V2: Hybrid daily qualification (looser — no EMA21 touch for trend pullback,
    no stochastic filter for mean reversion)

Identifies over/under-signaling and proposes V2.1 calibration.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicator_research import compute_indicators
from options_backtester import (
    OptionsBacktester, DEFAULTS, TICKER_ARCHETYPE,
    gen_trend_pullback_signals, gen_momentum_breakout_signals,
    gen_mean_reversion_signals,
)

TICKERS = ["SPY", "QQQ", "IWM", "SLV", "GLD", "XLE", "XLF",
           "NVDA", "TSLA", "AMD", "MSFT", "META", "AMZN", "SOFI", "INTC"]
FOCUS_START = "2024-01-01"


def run_v2_backtest(df, archetype):
    """Run options backtest using V2's LOOSER daily qualification conditions."""
    ind = compute_indicators(df)
    close = df["Close"]
    ema9 = ind["ema9"]
    ema21 = ind["ema21"]
    rsi = ind["rsi14"]
    hist = ind["histogram"]
    donch_hi = ind["donchian_high"]
    donch_lo = ind["donchian_low"]
    vol = df["Volume"]
    vol_sma = ind["vol_sma20"]
    bb_lo = ind["bb_lower"]
    bb_up = ind["bb_upper"]
    bb_mid = ind["bb_mid"]
    atr = ind["atr"]
    swing_lo = ind["swing_lo"]
    swing_hi = ind["swing_hi"]

    if archetype == "trend_pullback":
        long_sig = (ema9 > ema21) & (rsi > 50) & (hist > 0) & (close > ema21)
        short_sig = (ema9 < ema21) & (rsi < 50) & (hist < 0) & (close < ema21)
    elif archetype == "momentum_breakout":
        vol_spike = vol > vol_sma * 1.5
        long_sig = (close > donch_hi.shift(1)) & vol_spike
        short_sig = (close < donch_lo.shift(1)) & vol_spike
    else:
        macd_flip_up = (hist > 0) & (hist.shift(1) <= 0)
        bb_bounce = (df["Low"].shift(1) <= bb_lo.shift(1)) & (close > bb_lo)
        long_sig = macd_flip_up | bb_bounce
        macd_flip_dn = (hist < 0) & (hist.shift(1) >= 0)
        bb_reject = (df["High"].shift(1) >= bb_up.shift(1)) & (close < bb_up)
        short_sig = macd_flip_dn | bb_reject

    long_sig = long_sig.fillna(False)
    short_sig = short_sig.fillna(False)

    # Simulate trades with options 3-outcome model
    from options_backtester import OptionsTrade
    p = DEFAULTS
    dates = df.index
    n = len(df)
    trades = []
    in_trade = False
    pending = False
    pend_dir = ""
    pend_bar = 0
    entry_bar = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    last_sig_close = 0.0
    swing_active = False
    last_exit_bar = -10
    contracts = 1

    for i in range(1, n):
        if dates[i] < pd.Timestamp(FOCUS_START):
            continue
        c = close.iat[i]
        if np.isnan(atr.iat[i]) or atr.iat[i] <= 0:
            continue

        if pending and not in_trade and i == pend_bar + 1:
            entry_price = df["Open"].iat[i] + 0.01
            a = atr.iat[i]
            premium = a * p["premium_atr_ratio"]
            contracts = max(1, int(p["risk_budget"] / max(premium, 0.01)))
            if pend_dir == "long":
                sw = swing_lo.iat[i] if not np.isnan(swing_lo.iat[i]) else entry_price - 2 * a
                stop_price = max(sw, entry_price - p["atr_stop_mult"] * a)
                target_price = entry_price + p["atr_target_mult"] * a
            else:
                sw = swing_hi.iat[i] if not np.isnan(swing_hi.iat[i]) else entry_price + 2 * a
                stop_price = min(sw, entry_price + p["atr_stop_mult"] * a)
                target_price = entry_price - p["atr_target_mult"] * a
            in_trade = True
            entry_bar = i
            last_sig_close = c
            swing_active = True
            pending = False

        if in_trade:
            bars_held = i - entry_bar
            bh = df["High"].iat[i]
            bl = df["Low"].iat[i]
            if pend_dir == "long":
                sl_hit = bl <= stop_price
                tp_hit = bh >= target_price
            else:
                sl_hit = bh >= stop_price
                tp_hit = bl <= target_price

            outcome = None
            exit_price = c
            if sl_hit and tp_hit:
                outcome = "LOSS"
                exit_price = stop_price
            elif sl_hit:
                outcome = "LOSS"
                exit_price = stop_price
            elif tp_hit:
                outcome = "WIN"
                exit_price = target_price
            elif bars_held >= p["max_hold_bars"]:
                outcome = "FLAT_LOSS"

            if outcome:
                premium = atr.iat[entry_bar] * p["premium_atr_ratio"]
                if outcome == "WIN":
                    pnl = premium * 0.5 * contracts
                elif outcome == "FLAT_LOSS":
                    pnl = -premium * 0.5 * contracts
                else:
                    pnl = -premium * contracts
                trades.append(OptionsTrade(
                    dates[entry_bar], dates[i], pend_dir, entry_price, exit_price,
                    stop_price, target_price, outcome, round(pnl, 2), bars_held,
                    archetype, "v2_qual", contracts,
                ))
                in_trade = False
                swing_active = False
                last_exit_bar = i
                continue

        if in_trade:
            continue
        if i - last_exit_bar < 5:
            continue
        if swing_active and last_sig_close > 0:
            pullback = abs(c - last_sig_close) / last_sig_close
            if pullback < 0.02:
                continue
            swing_active = False

        if long_sig.iat[i]:
            pending = True
            pend_dir = "long"
            pend_bar = i
        elif short_sig.iat[i]:
            pending = True
            pend_dir = "short"
            pend_bar = i

    return trades


def summarize(trades):
    """Summarize a list of OptionsTrade objects."""
    if not trades:
        return {"total": 0, "win_rate": 0, "flat_rate": 0, "loss_rate": 0,
                "profit_factor": 0, "net_pnl": 0}
    n = len(trades)
    wins = sum(1 for t in trades if t.outcome == "WIN")
    flats = sum(1 for t in trades if t.outcome == "FLAT_LOSS")
    losses = sum(1 for t in trades if t.outcome == "LOSS")
    gp = sum(t.pnl for t in trades if t.pnl > 0)
    gl = abs(sum(t.pnl for t in trades if t.pnl <= 0))
    return {
        "total": n,
        "win_rate": round(100 * wins / n, 1),
        "flat_rate": round(100 * flats / n, 1),
        "loss_rate": round(100 * losses / n, 1),
        "profit_factor": round(gp / gl, 2) if gl > 0 else (float("inf") if gp > 0 else 0),
        "net_pnl": round(sum(t.pnl for t in trades), 0),
    }


def count_v1_signals(df, archetype):
    """Count V1 signals (original archetype conditions)."""
    ind = compute_indicators(df)
    if archetype == "trend_pullback":
        long_sig, short_sig, _ = gen_trend_pullback_signals(df, ind)
    elif archetype == "momentum_breakout":
        long_sig, short_sig, _ = gen_momentum_breakout_signals(df, ind)
    else:
        long_sig, short_sig, _ = gen_mean_reversion_signals(df, ind)

    focus = df.index >= pd.Timestamp(FOCUS_START)
    return long_sig[focus].sum(), short_sig[focus].sum()


def count_v2_daily_qualification(df, archetype):
    """Count V2 daily qualification signals (LOOSER conditions)."""
    ind = compute_indicators(df)
    close = df["Close"]
    ema9 = ind["ema9"]
    ema21 = ind["ema21"]
    rsi = ind["rsi14"]
    hist = ind["histogram"]
    donch_hi = ind["donchian_high"]
    donch_lo = ind["donchian_low"]
    vol = df["Volume"]
    vol_sma = ind["vol_sma20"]
    bb_lo = ind["bb_lower"]
    bb_up = ind["bb_upper"]
    bb_mid = ind["bb_mid"]
    low = df["Low"]
    high = df["High"]

    if archetype == "trend_pullback":
        # V2: NO EMA21 touch requirement (the key difference)
        long_sig = (ema9 > ema21) & (rsi > 50) & (hist > 0) & (close > ema21)
        short_sig = (ema9 < ema21) & (rsi < 50) & (hist < 0) & (close < ema21)
    elif archetype == "momentum_breakout":
        # V2: Same as V1
        vol_spike = vol > vol_sma * 1.5
        long_sig = (close > donch_hi.shift(1)) & vol_spike
        short_sig = (close < donch_lo.shift(1)) & vol_spike
    else:
        # V2: NO stochastic filter, NO BB mid check (looser)
        macd_flip_up = (hist > 0) & (hist.shift(1) <= 0)
        bb_bounce = (low.shift(1) <= bb_lo.shift(1)) & (close > bb_lo)
        long_sig = macd_flip_up | bb_bounce

        macd_flip_dn = (hist < 0) & (hist.shift(1) >= 0)
        bb_reject = (high.shift(1) >= bb_up.shift(1)) & (close < bb_up)
        short_sig = macd_flip_dn | bb_reject

    focus = df.index >= pd.Timestamp(FOCUS_START)
    return long_sig.fillna(False)[focus].sum(), short_sig.fillna(False)[focus].sum()


def main():
    print("=" * 70)
    print("  V1 vs V2 SIGNAL FREQUENCY + WIN RATE + PROFITABILITY")
    print(f"  Period: {FOCUS_START} to present")
    print("=" * 70)

    rows = []
    for ticker in TICKERS:
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception:
            continue

        archetype = TICKER_ARCHETYPE.get(ticker, "trend_pullback")
        months = (df.index[-1] - pd.Timestamp(FOCUS_START)).days / 30.44

        # V1: full backtest with original conditions
        bt_v1 = OptionsBacktester(ticker, archetype)
        log_v1 = bt_v1.run(df)
        s_v1 = log_v1.summary()

        # V2: backtest with looser daily qualification (simulated)
        # Create a modified backtester that uses V2's looser conditions
        v2_trades = run_v2_backtest(df, archetype)
        s_v2 = summarize(v2_trades)

        v1_mo = s_v1["total"] / months if months > 0 else 0
        v2_mo = s_v2["total"] / months if months > 0 else 0

        # Target range
        target_lo, target_hi = 2.0, 6.0
        if v2_mo > target_hi:
            diag = "V2 NOISY"
        elif v2_mo < target_lo and v1_mo < target_lo:
            diag = "BOTH QUIET"
        elif target_lo <= v2_mo <= target_hi:
            diag = "V2 OK"
        elif target_lo <= v1_mo <= target_hi:
            diag = "V1 OK"
        else:
            diag = "TUNE"

        rows.append({
            "Ticker": ticker, "Arch": archetype[:6],
            "V1_N": s_v1["total"], "V1/Mo": round(v1_mo, 1),
            "V1_WR": s_v1.get("win_rate", 0), "V1_Flat": s_v1.get("flat_rate", 0),
            "V1_PF": s_v1.get("profit_factor", 0), "V1_PnL": s_v1.get("net_pnl", 0),
            "V2_N": s_v2["total"], "V2/Mo": round(v2_mo, 1),
            "V2_WR": s_v2.get("win_rate", 0), "V2_Flat": s_v2.get("flat_rate", 0),
            "V2_PF": s_v2.get("profit_factor", 0), "V2_PnL": s_v2.get("net_pnl", 0),
            "Diag": diag,
        })

    print()
    # Print in two sections for readability
    print("  SIGNAL FREQUENCY:")
    freq_cols = ["Ticker", "Arch", "V1_N", "V1/Mo", "V2_N", "V2/Mo", "Diag"]
    print(tabulate([{k: r[k] for k in freq_cols} for r in rows],
                   headers="keys", tablefmt="simple", floatfmt=".1f"))

    print(f"\n  WIN RATE & PROFITABILITY:")
    perf_cols = ["Ticker", "V1_WR", "V1_Flat", "V1_PF", "V1_PnL", "V2_WR", "V2_Flat", "V2_PF", "V2_PnL"]
    print(tabulate([{k: r[k] for k in perf_cols} for r in rows],
                   headers="keys", tablefmt="simple", floatfmt=".1f"))

    # Aggregate
    v1_total_pnl = sum(r["V1_PnL"] for r in rows)
    v2_total_pnl = sum(r["V2_PnL"] for r in rows)
    v1_avg_wr = np.mean([r["V1_WR"] for r in rows if r["V1_N"] > 0])
    v2_avg_wr = np.mean([r["V2_WR"] for r in rows if r["V2_N"] > 0])

    print(f"\n  AGGREGATE:")
    print(f"    V1: ${v1_total_pnl:,.0f} total PnL, {v1_avg_wr:.1f}% avg WR")
    print(f"    V2: ${v2_total_pnl:,.0f} total PnL, {v2_avg_wr:.1f}% avg WR")
    print(f"    Delta: ${v2_total_pnl - v1_total_pnl:+,.0f} PnL, {v2_avg_wr - v1_avg_wr:+.1f}% WR")

    # V2.1 Recommendations with profitability context
    print(f"\n{'=' * 70}")
    print("  V2.1 CALIBRATION RECOMMENDATIONS (with profitability)")
    print(f"{'=' * 70}")

    recs = []
    for r in rows:
        ticker = r["Ticker"]
        v1_better = r["V1_PF"] > r["V2_PF"] and r["V1_WR"] > r["V2_WR"]
        v2_better = r["V2_PF"] > r["V1_PF"] and r["V2_WR"] > r["V1_WR"]

        if r["Diag"] == "V2 NOISY" and v1_better:
            rec = "V2.1: reintroduce pullback + tighter RSI"
            reason = f"V2 noisy ({r['V2/Mo']:.0f}/mo) and V1 more profitable (PF {r['V1_PF']:.2f} vs {r['V2_PF']:.2f})"
        elif r["Diag"] == "V2 NOISY" and not v1_better:
            rec = "V2.1: raise cooldown to 3%, keep V2 conditions"
            reason = f"V2 noisy but more profitable — just reduce frequency"
        elif r["Diag"] == "V2 OK":
            rec = "Use V2 as-is"
            reason = f"On target ({r['V2/Mo']:.1f}/mo), WR={r['V2_WR']:.0f}%"
        elif r["Diag"] == "V1 OK":
            rec = "Use V1 settings"
            reason = f"V1 on target ({r['V1/Mo']:.1f}/mo), WR={r['V1_WR']:.0f}%"
        elif r["Diag"] == "BOTH QUIET":
            rec = "V2 loosened: score 60, cooldown 1.5%"
            reason = f"Both versions too quiet"
        else:
            rec = "Custom tuning needed"
            reason = f"Neither version ideal"

        recs.append({"Ticker": ticker, "Rec": rec, "V2/Mo": r["V2/Mo"],
                     "Best_WR": max(r["V1_WR"], r["V2_WR"]),
                     "Best_PF": max(r["V1_PF"], r["V2_PF"]),
                     "Reason": reason})

    print()
    print(tabulate(recs, headers="keys", tablefmt="simple", floatfmt=".1f"))

    # Write report
    report = ["# V1 vs V2 Signal + Performance Comparison", ""]
    report.append(f"*{FOCUS_START} to present, 15 tickers, options 3-outcome model*")
    report.append("")
    report.append("## Signal Frequency")
    report.append("")
    report.append("| Ticker | Arch | V1/Mo | V2/Mo | Diagnosis |")
    report.append("|--------|------|-------|-------|-----------|")
    for r in rows:
        report.append(f"| {r['Ticker']} | {r['Arch']} | {r['V1/Mo']:.1f} | {r['V2/Mo']:.1f} | {r['Diag']} |")
    report.append("")
    report.append("## Win Rate & Profitability")
    report.append("")
    report.append("| Ticker | V1 WR | V1 Flat% | V1 PF | V1 PnL | V2 WR | V2 Flat% | V2 PF | V2 PnL |")
    report.append("|--------|-------|---------|-------|--------|-------|---------|-------|--------|")
    for r in rows:
        report.append(f"| {r['Ticker']} | {r['V1_WR']:.0f}% | {r['V1_Flat']:.0f}% | {r['V1_PF']:.2f} | "
                      f"${r['V1_PnL']:.0f} | {r['V2_WR']:.0f}% | {r['V2_Flat']:.0f}% | "
                      f"{r['V2_PF']:.2f} | ${r['V2_PnL']:.0f} |")
    report.append("")
    report.append(f"## Aggregate: V1 ${v1_total_pnl:,.0f} vs V2 ${v2_total_pnl:,.0f}")
    report.append("")
    report.append("## V2.1 Recommendations")
    report.append("")
    report.append("| Ticker | Recommendation | Signals/Mo | Best WR | Best PF | Reason |")
    report.append("|--------|---------------|-----------|---------|---------|--------|")
    for r in recs:
        report.append(f"| {r['Ticker']} | {r['Rec']} | {r['V2/Mo']:.1f} | "
                      f"{r['Best_WR']:.0f}% | {r['Best_PF']:.2f} | {r['Reason']} |")

    out = Path("reports") / "v1_vs_v2_comparison.md"
    out.write_text("\n".join(report))
    print(f"\n  Report: {out}")


if __name__ == "__main__":
    main()
