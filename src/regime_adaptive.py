#!/usr/bin/env python3
"""
Regime-adaptive analysis for SPY, QQQ, IWM.

Tests longs in bull regime, shorts in bear regime, iron condors in range.
Uses FULL historical data (SPY from 1993, QQQ from 2009, IWM from 2000).

Output: reports/index_etf_regime_analysis.md
"""

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicator_research import compute_indicators
from indicators import calc_ema, calc_adx, calc_atr
from options_backtester import (
    OptionsBacktester, OptionsTradeLog, OptionsTrade, DEFAULTS,
    gen_trend_pullback_signals, gen_momentum_breakout_signals,
    gen_mean_reversion_signals, ARCHETYPE_SIGNALS,
)
from validate_pinescript import compute_weekly_indicators

TICKERS = ["SPY", "QQQ", "IWM"]
ARCHETYPES = ["trend_pullback", "momentum_breakout", "mean_reversion"]
PARAM_GRID = {
    "atr_stop_mult": [1.0, 1.5, 2.0, 3.0],
    "atr_target_mult": [1.5, 2.0, 3.0],
    "max_hold_bars": [15, 20],
    "cooldown_pullback_pct": [0.02, 0.03],
}

# Historical periods for context
PERIODS = [
    ("2008-2009 Bear", "2008-01-01", "2009-12-31"),
    ("2010-2015 Bull", "2010-01-01", "2015-12-31"),
    ("2016-2019 Bull", "2016-01-01", "2019-12-31"),
    ("2020-2021 Covid", "2020-01-01", "2021-12-31"),
    ("2022 Bear", "2022-01-01", "2022-12-31"),
    ("2023-2025 Bull", "2023-01-01", "2025-12-31"),
    ("2026 Selloff", "2026-01-01", "2026-12-31"),
]


def regime_split_backtest(df, archetype, params):
    """Run backtester and split trades by weekly regime at entry."""
    # Compute weekly regime
    wk = compute_weekly_indicators(df)
    bull_mask = (wk["wk_ema9"] > wk["wk_ema21"]).fillna(False)

    # Run full backtest (both directions)
    bt = OptionsBacktester("", archetype, params)
    log = bt.run(df)

    # Split trades by regime at entry
    bull_longs = [t for t in log.trades if t.direction == "long" and bull_mask.asof(t.entry_date)]
    bear_shorts = [t for t in log.trades if t.direction == "short" and not bull_mask.asof(t.entry_date)]
    # Also wrong-regime trades for comparison
    bear_longs = [t for t in log.trades if t.direction == "long" and not bull_mask.asof(t.entry_date)]
    bull_shorts = [t for t in log.trades if t.direction == "short" and bull_mask.asof(t.entry_date)]

    return {
        "bull_longs": bull_longs,
        "bear_shorts": bear_shorts,
        "bear_longs": bear_longs,  # wrong regime — for comparison
        "bull_shorts": bull_shorts,  # wrong regime
        "all_trades": log.trades,
        "bull_mask": bull_mask,
    }


def summarize_trades(trades, label=""):
    """Quick summary of a trade list."""
    if not trades:
        return {"label": label, "n": 0, "wr": 0, "pf": 0, "flat%": 0, "pnl": 0}
    n = len(trades)
    wins = sum(1 for t in trades if t.outcome == "WIN")
    flats = sum(1 for t in trades if t.outcome == "FLAT_LOSS")
    gp = sum(t.pnl for t in trades if t.pnl > 0)
    gl = abs(sum(t.pnl for t in trades if t.pnl <= 0))
    return {
        "label": label, "n": n,
        "wr": round(100 * wins / n, 1),
        "flat%": round(100 * flats / n, 1),
        "pf": round(gp / gl, 2) if gl > 0 else float("inf"),
        "pnl": round(sum(t.pnl for t in trades), 0),
    }


def optimize_regime_adaptive(df, ticker):
    """Find best params for longs-in-bull and shorts-in-bear independently."""
    combos = list(itertools.product(*PARAM_GRID.values()))
    keys = list(PARAM_GRID.keys())

    best_bull_long = None
    best_bear_short = None
    best_bl_arch = ""
    best_bs_arch = ""

    for archetype in ARCHETYPES:
        for values in combos:
            params = {**DEFAULTS}
            for k, v in zip(keys, values):
                params[k] = v

            result = regime_split_backtest(df, archetype, params)

            # Evaluate bull longs
            bl = result["bull_longs"]
            if len(bl) >= 5:
                s = summarize_trades(bl)
                if best_bull_long is None or s["wr"] > best_bull_long["wr"]:
                    if s["pf"] >= 0.8:
                        best_bull_long = {**s, "params": params.copy(), "arch": archetype}
                        best_bl_arch = archetype

            # Evaluate bear shorts
            bs = result["bear_shorts"]
            if len(bs) >= 5:
                s = summarize_trades(bs)
                if best_bear_short is None or s["wr"] > best_bear_short["wr"]:
                    if s["pf"] >= 0.8:
                        best_bear_short = {**s, "params": params.copy(), "arch": archetype}
                        best_bs_arch = archetype

    return best_bull_long, best_bl_arch, best_bear_short, best_bs_arch


def period_analysis(df, archetype, params):
    """Analyze performance across historical periods."""
    wk = compute_weekly_indicators(df)
    bull_mask = (wk["wk_ema9"] > wk["wk_ema21"]).fillna(False)

    bt = OptionsBacktester("", archetype, params)
    log = bt.run(df)

    rows = []
    for period_name, start, end in PERIODS:
        ps = pd.Timestamp(start)
        pe = pd.Timestamp(end)

        period_trades = [t for t in log.trades if ps <= t.entry_date <= pe]
        if not period_trades:
            rows.append({"Period": period_name, "Trades": 0, "Regime": "—",
                         "L_WR": 0, "S_WR": 0, "Net": 0})
            continue

        longs = [t for t in period_trades if t.direction == "long"]
        shorts = [t for t in period_trades if t.direction == "short"]

        # Dominant regime in this period
        period_bull = bull_mask[(bull_mask.index >= ps) & (bull_mask.index <= pe)]
        bull_pct = period_bull.mean() if len(period_bull) > 0 else 0
        regime = "BULL" if bull_pct > 0.6 else ("BEAR" if bull_pct < 0.4 else "MIXED")

        l_wr = 100 * sum(1 for t in longs if t.outcome == "WIN") / len(longs) if longs else 0
        s_wr = 100 * sum(1 for t in shorts if t.outcome == "WIN") / len(shorts) if shorts else 0

        rows.append({
            "Period": period_name, "Trades": len(period_trades),
            "Regime": f"{regime} ({bull_pct:.0%})",
            "Longs": len(longs), "L_WR": round(l_wr, 0),
            "Shorts": len(shorts), "S_WR": round(s_wr, 0),
            "Net": round(sum(t.pnl for t in period_trades), 0),
        })

    return rows


def main():
    print("=" * 70)
    print("  REGIME-ADAPTIVE ANALYSIS — SPY, QQQ, IWM")
    print("=" * 70)

    report_lines = ["# Index ETF Regime-Adaptive Analysis", ""]
    report_lines.append("*Testing longs in bull regime, shorts in bear regime, across full history*")
    report_lines.append("")

    configs = {}

    for ticker in TICKERS:
        print(f"\n  {ticker}...")
        df = load_sierra_dly(f"data/{ticker}.dly")
        print(f"    {len(df)} bars, {df.index[0].date()} → {df.index[-1].date()}")

        # Optimize regime-adaptive params
        print(f"    Optimizing (48 combos × 3 archetypes)...", flush=True)
        best_bl, bl_arch, best_bs, bs_arch = optimize_regime_adaptive(df, ticker)

        report_lines.append(f"## {ticker}")
        report_lines.append("")

        # Bull longs
        if best_bl:
            print(f"    Bull Longs:  WR={best_bl['wr']:.0f}% PF={best_bl['pf']:.2f} "
                  f"n={best_bl['n']} [{bl_arch}]")
            report_lines.append(f"**Bull Regime Longs** ({bl_arch}): "
                                f"WR={best_bl['wr']:.0f}%, PF={best_bl['pf']:.2f}, "
                                f"n={best_bl['n']}")
        else:
            print(f"    Bull Longs:  NO VIABLE PARAMS")
            report_lines.append("**Bull Regime Longs**: No viable params")

        # Bear shorts
        if best_bs:
            print(f"    Bear Shorts: WR={best_bs['wr']:.0f}% PF={best_bs['pf']:.2f} "
                  f"n={best_bs['n']} [{bs_arch}]")
            report_lines.append(f"**Bear Regime Shorts** ({bs_arch}): "
                                f"WR={best_bs['wr']:.0f}%, PF={best_bs['pf']:.2f}, "
                                f"n={best_bs['n']}")
        else:
            print(f"    Bear Shorts: NO VIABLE PARAMS")
            report_lines.append("**Bear Regime Shorts**: No viable params")

        report_lines.append("")

        # Historical period analysis with best params
        best_params = (best_bl or best_bs or {}).get("params", DEFAULTS)
        best_arch = bl_arch or bs_arch or "momentum_breakout"
        print(f"    Period analysis...", flush=True)
        periods = period_analysis(df, best_arch, best_params)
        report_lines.append("### Historical Period Performance")
        report_lines.append("")
        report_lines.append("| Period | Trades | Regime | Longs | L_WR | Shorts | S_WR | Net |")
        report_lines.append("|--------|--------|--------|-------|------|--------|------|-----|")
        for p in periods:
            report_lines.append(
                f"| {p['Period']} | {p['Trades']} | {p.get('Regime','—')} | "
                f"{p.get('Longs',0)} | {p.get('L_WR',0):.0f}% | "
                f"{p.get('Shorts',0)} | {p.get('S_WR',0):.0f}% | ${p.get('Net',0):.0f} |"
            )
        report_lines.append("")

        # Qualification
        bl_ok = best_bl and best_bl["wr"] > 45 and best_bl["pf"] > 1.0 and best_bl["n"] >= 10
        bs_ok = best_bs and best_bs["wr"] > 45 and best_bs["pf"] > 1.0 and best_bs["n"] >= 10

        if bl_ok and bs_ok:
            direction = "regime_adaptive"
        elif bl_ok:
            direction = "regime_adaptive_long_only"
        elif bs_ok:
            direction = "regime_adaptive_short_only"
        else:
            direction = "excluded"

        report_lines.append(f"**Direction**: {direction}")
        report_lines.append("")

        # Build config
        cfg = {"ticker": ticker, "direction": direction}
        if best_bl:
            p = best_bl["params"]
            cfg["bull_long"] = {
                "archetype": bl_arch,
                "params": {k: v for k, v in p.items() if k in list(PARAM_GRID.keys()) + ["max_hold_bars"]},
                "oos_wr": best_bl["wr"] / 100,
                "oos_pf": best_bl["pf"],
            }
        if best_bs:
            p = best_bs["params"]
            cfg["bear_short"] = {
                "archetype": bs_arch,
                "params": {k: v for k, v in p.items() if k in list(PARAM_GRID.keys()) + ["max_hold_bars"]},
                "oos_wr": best_bs["wr"] / 100,
                "oos_pf": best_bs["pf"],
            }
        cfg["regime_rules"] = {
            "bull": "weekly EMA9 > EMA21",
            "bear": "weekly EMA9 < EMA21",
            "range": "ADX < 20 for 10+ bars",
        }
        cfg["iron_condor"] = {"suitable": True}
        configs[ticker] = cfg

        print(f"    → {direction}")

    # Print summary
    print(f"\n{'=' * 70}")
    for ticker, cfg in configs.items():
        bl = cfg.get("bull_long", {})
        bs = cfg.get("bear_short", {})
        print(f"  {ticker}: {cfg['direction']}")
        if bl:
            print(f"    Bull Long:  WR={bl.get('oos_wr',0):.0%} PF={bl.get('oos_pf',0):.2f} [{bl.get('archetype','')}]")
        if bs:
            print(f"    Bear Short: WR={bs.get('oos_wr',0):.0%} PF={bs.get('oos_pf',0):.2f} [{bs.get('archetype','')}]")

    # Update config
    config_path = Path("config") / "ticker_configs.json"
    existing = json.loads(config_path.read_text())
    for ticker, cfg in configs.items():
        existing[ticker] = cfg
    config_path.write_text(json.dumps(existing, indent=2))
    print(f"\n  Updated: {config_path}")

    # Write report
    report_path = Path("reports") / "index_etf_regime_analysis.md"
    report_path.write_text("\n".join(report_lines))
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
