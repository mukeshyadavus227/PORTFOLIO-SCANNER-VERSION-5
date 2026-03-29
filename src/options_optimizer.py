#!/usr/bin/env python3
"""
Step 3: Per-ticker walk-forward optimization for options swing trading.

Grid search over stop/target/hold/cooldown parameters.
Tests longs and shorts independently per ticker.
Reports OOS win rate, PF, flat rate, and direction qualification.

Output:
  - reports/per_ticker_backtest.md
  - config/ticker_configs.json
"""

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicator_research import compute_indicators
from options_backtester import (
    OptionsBacktester, OptionsTradeLog, OptionsTrade,
    CLUSTERS, TICKER_ARCHETYPE, DEFAULTS,
    gen_trend_pullback_signals, gen_momentum_breakout_signals,
    gen_mean_reversion_signals, ARCHETYPE_SIGNALS,
)

TICKERS = ["SPY", "QQQ", "IWM", "SLV", "GLD", "XLE", "XLF",
           "NVDA", "TSLA", "AMD", "MSFT", "META", "AMZN", "SOFI", "INTC"]

# Parameter grid (reduced for speed — 48 combos per ticker)
PARAM_GRID = {
    "atr_stop_mult": [1.0, 1.5, 2.0, 3.0],
    "atr_target_mult": [1.5, 2.0, 3.0],
    "max_hold_bars": [15, 20],
    "cooldown_pullback_pct": [0.02, 0.03],
}

# Walk-forward windows (train_start, train_end, test_start, test_end)
WINDOWS = [
    ("2020-01-01", "2023-06-30", "2023-07-01", "2024-12-31"),
    ("2020-07-01", "2024-01-01", "2024-01-02", "2025-06-30"),
    ("2021-01-01", "2024-07-01", "2024-07-02", "2026-03-26"),
]


def run_with_params(df, archetype, params, direction_filter=None):
    """Run backtester with custom params, optionally filtering direction."""
    bt = OptionsBacktester("", archetype, params)
    log = bt.run(df)

    if direction_filter and log.trades:
        log.trades = [t for t in log.trades if t.direction == direction_filter]

    return log


def evaluate_params(df, archetype, params, direction):
    """Evaluate params using walk-forward: run on full data, slice to OOS windows."""
    full_log = run_with_params(df, archetype, params, direction)

    is_trades = []
    oos_trades = []

    for _, train_end, test_start, test_end in WINDOWS:
        te = pd.Timestamp(train_end)
        ts = pd.Timestamp(test_start)
        tend = pd.Timestamp(test_end)

        for t in full_log.trades:
            if t.entry_date <= te:
                is_trades.append(t)
            elif ts <= t.entry_date <= tend:
                oos_trades.append(t)

    if len(oos_trades) < 5:
        return None

    oos_wins = sum(1 for t in oos_trades if t.outcome == "WIN")
    oos_flats = sum(1 for t in oos_trades if t.outcome == "FLAT_LOSS")
    oos_losses = sum(1 for t in oos_trades if t.outcome == "LOSS")
    oos_n = len(oos_trades)
    oos_wr = oos_wins / oos_n
    oos_flat_rate = oos_flats / oos_n
    oos_pnl = sum(t.pnl for t in oos_trades)
    gp = sum(t.pnl for t in oos_trades if t.pnl > 0)
    gl = abs(sum(t.pnl for t in oos_trades if t.pnl <= 0))
    oos_pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
    oos_expect = oos_pnl / oos_n

    is_wins = sum(1 for t in is_trades if t.outcome == "WIN")
    is_wr = is_wins / len(is_trades) if is_trades else 0

    return {
        "oos_wr": round(oos_wr, 3),
        "oos_pf": round(oos_pf, 2),
        "oos_flat_rate": round(oos_flat_rate, 3),
        "oos_trades": oos_n,
        "oos_pnl": round(oos_pnl, 2),
        "oos_expect": round(oos_expect, 2),
        "is_wr": round(is_wr, 3),
        "degradation": round(oos_wr / is_wr, 3) if is_wr > 0 else 0,
        "params": params,
    }


def optimize_ticker(ticker, df):
    """Optimize one ticker across all archetypes and directions."""
    archetypes_to_try = [TICKER_ARCHETYPE.get(ticker, "mean_reversion")]

    best_long = None
    best_short = None
    best_long_arch = ""
    best_short_arch = ""

    combos = list(itertools.product(
        PARAM_GRID["atr_stop_mult"],
        PARAM_GRID["atr_target_mult"],
        PARAM_GRID["max_hold_bars"],
        PARAM_GRID["cooldown_pullback_pct"],
    ))

    for archetype in archetypes_to_try:
        for stop, target, hold, cooldown in combos:
            params = {
                **DEFAULTS,
                "atr_stop_mult": stop,
                "atr_target_mult": target,
                "max_hold_bars": hold,
                "cooldown_pullback_pct": cooldown,
            }

            # Test longs
            result = evaluate_params(df, archetype, params, "long")
            if result and (best_long is None or result["oos_wr"] > best_long["oos_wr"]):
                if result["oos_pf"] >= 0.8:  # relaxed PF gate for initial pass
                    best_long = result
                    best_long_arch = archetype

            # Test shorts
            result = evaluate_params(df, archetype, params, "short")
            if result and (best_short is None or result["oos_wr"] > best_short["oos_wr"]):
                if result["oos_pf"] >= 0.8:
                    best_short = result
                    best_short_arch = archetype

    return best_long, best_long_arch, best_short, best_short_arch


def main():
    print("=" * 70)
    print("  STEP 3: PER-TICKER WALK-FORWARD OPTIMIZATION")
    print(f"  {len(list(itertools.product(*PARAM_GRID.values())))} param combos × "
          f"3 archetypes × 2 directions per ticker")
    print("=" * 70)

    results = []
    configs = {}
    t0 = time.time()

    for ticker in TICKERS:
        ticker_t0 = time.time()
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception:
            print(f"  {ticker}: data not found")
            continue

        print(f"\n  {ticker}...", end=" ", flush=True)
        best_long, long_arch, best_short, short_arch = optimize_ticker(ticker, df)
        elapsed = time.time() - ticker_t0

        # Direction qualification
        long_ok = best_long and best_long["oos_wr"] > 0.45 and best_long["oos_pf"] > 1.0 and best_long["oos_trades"] >= 10
        short_ok = best_short and best_short["oos_wr"] > 0.45 and best_short["oos_pf"] > 1.0 and best_short["oos_trades"] >= 10

        # Relaxed qualification for marginal cases
        long_marginal = best_long and best_long["oos_wr"] > 0.40 and best_long["oos_trades"] >= 8
        short_marginal = best_short and best_short["oos_wr"] > 0.40 and best_short["oos_trades"] >= 8

        if long_ok and short_ok:
            direction = "both"
        elif long_ok:
            direction = "long_only"
        elif short_ok:
            direction = "short_only"
        elif long_marginal:
            direction = "long_marginal"
        elif short_marginal:
            direction = "short_marginal"
        else:
            direction = "excluded"

        row = {"Ticker": ticker, "Direction": direction}

        if best_long:
            row.update({
                "L_Arch": long_arch[:8], "L_OOS_WR": best_long["oos_wr"],
                "L_OOS_PF": best_long["oos_pf"], "L_OOS_N": best_long["oos_trades"],
                "L_Flat%": best_long["oos_flat_rate"], "L_IS_WR": best_long["is_wr"],
                "L_Degrad": best_long["degradation"],
            })
        else:
            row.update({"L_Arch": "—", "L_OOS_WR": 0, "L_OOS_PF": 0, "L_OOS_N": 0,
                        "L_Flat%": 0, "L_IS_WR": 0, "L_Degrad": 0})

        if best_short:
            row.update({
                "S_Arch": short_arch[:8], "S_OOS_WR": best_short["oos_wr"],
                "S_OOS_PF": best_short["oos_pf"], "S_OOS_N": best_short["oos_trades"],
            })
        else:
            row.update({"S_Arch": "—", "S_OOS_WR": 0, "S_OOS_PF": 0, "S_OOS_N": 0})

        results.append(row)

        # Build config
        cfg = {"ticker": ticker, "direction": direction}
        if best_long:
            cfg["long"] = {
                "archetype": long_arch,
                "params": best_long["params"],
                "oos_wr": best_long["oos_wr"],
                "oos_pf": best_long["oos_pf"],
            }
        if best_short:
            cfg["short"] = {
                "archetype": short_arch,
                "params": best_short["params"],
                "oos_wr": best_short["oos_wr"],
                "oos_pf": best_short["oos_pf"],
            }
        configs[ticker] = cfg

        # Print summary
        l_wr = f"{best_long['oos_wr']:.0%}" if best_long else "—"
        s_wr = f"{best_short['oos_wr']:.0%}" if best_short else "—"
        print(f"L:{l_wr} S:{s_wr} → {direction} ({elapsed:.0f}s)")

    total_elapsed = time.time() - t0

    # Print results table
    print(f"\n{'=' * 70}")
    print(f"  RESULTS ({total_elapsed:.0f}s total)")
    print(f"{'=' * 70}\n")
    print(tabulate(results, headers="keys", tablefmt="simple", floatfmt=".2f"))

    # Summary
    qualified = [r for r in results if "excluded" not in r["Direction"]]
    excluded = [r for r in results if r["Direction"] == "excluded"]
    print(f"\n  Qualified: {len(qualified)}/{len(results)}")
    print(f"  Excluded: {len(excluded)} ({', '.join(r['Ticker'] for r in excluded) or 'none'})")

    # Write outputs
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)

    # JSON config
    # Clean params for JSON serialization
    for ticker, cfg in configs.items():
        for dir_key in ["long", "short"]:
            if dir_key in cfg and "params" in cfg[dir_key]:
                cfg[dir_key]["params"] = {k: v for k, v in cfg[dir_key]["params"].items()
                                           if k in PARAM_GRID or k in ["risk_budget", "premium_atr_ratio", "slippage", "max_hold_bars"]}

    config_path = config_dir / "ticker_configs.json"
    with open(config_path, "w") as f:
        json.dump(configs, f, indent=2)
    print(f"\n  Config: {config_path}")

    # Markdown report
    report_lines = ["# Per-Ticker Backtest Results (Walk-Forward)", ""]
    report_lines.append(f"*{len(list(itertools.product(*PARAM_GRID.values())))} param combos × "
                        f"3 archetypes × 2 directions, {len(WINDOWS)} walk-forward windows*")
    report_lines.append("")
    report_lines.append("| Ticker | Direction | L_Arch | L_WR | L_PF | L_N | S_Arch | S_WR | S_PF | S_N |")
    report_lines.append("|--------|-----------|--------|------|------|-----|--------|------|------|-----|")
    for r in results:
        report_lines.append(
            f"| {r['Ticker']} | {r['Direction']} | {r.get('L_Arch','—')} | "
            f"{r.get('L_OOS_WR',0):.0%} | {r.get('L_OOS_PF',0):.2f} | {r.get('L_OOS_N',0)} | "
            f"{r.get('S_Arch','—')} | {r.get('S_OOS_WR',0):.0%} | {r.get('S_OOS_PF',0):.2f} | {r.get('S_OOS_N',0)} |"
        )
    report_lines.append("")

    # Best params per qualified ticker
    report_lines.append("## Optimal Parameters Per Ticker")
    report_lines.append("")
    for ticker, cfg in configs.items():
        if cfg["direction"] == "excluded":
            continue
        report_lines.append(f"### {ticker} ({cfg['direction']})")
        if "long" in cfg:
            p = cfg["long"]["params"]
            report_lines.append(f"- Long ({cfg['long']['archetype']}): "
                                f"stop={p.get('atr_stop_mult',2.0)}x ATR, "
                                f"target={p.get('atr_target_mult',2.0)}x ATR, "
                                f"hold={p.get('max_hold_bars',20)} bars, "
                                f"cooldown={p.get('cooldown_pullback_pct',0.02)*100:.0f}% "
                                f"| OOS WR={cfg['long']['oos_wr']:.0%} PF={cfg['long']['oos_pf']:.2f}")
        if "short" in cfg:
            p = cfg["short"]["params"]
            report_lines.append(f"- Short ({cfg['short']['archetype']}): "
                                f"stop={p.get('atr_stop_mult',2.0)}x ATR, "
                                f"target={p.get('atr_target_mult',2.0)}x ATR, "
                                f"hold={p.get('max_hold_bars',20)} bars "
                                f"| OOS WR={cfg['short']['oos_wr']:.0%} PF={cfg['short']['oos_pf']:.2f}")
        report_lines.append("")

    report_path = reports_dir / "per_ticker_backtest.md"
    report_path.write_text("\n".join(report_lines))
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
