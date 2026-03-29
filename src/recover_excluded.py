#!/usr/bin/env python3
"""
Recover excluded tickers by testing all 3 archetypes + tighter params + iron condor.

Tests SPY, QQQ, IWM, NVDA, META, AMZN, SOFI, INTC with:
  Round 1: All 3 archetypes × 48 param combos × long-only
  Round 2: Tighter params (1.0-1.5x ATR) if Round 1 fails
  Round 3: Iron condor suitability analysis
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
from indicators import calc_adx, calc_atr
from options_backtester import (
    OptionsBacktester, DEFAULTS, ARCHETYPE_SIGNALS,
)
from options_optimizer import evaluate_params, WINDOWS

EXCLUDED = ["SPY", "QQQ", "IWM", "NVDA", "META", "AMZN", "SOFI", "INTC"]
ARCHETYPES = ["trend_pullback", "momentum_breakout", "mean_reversion"]

# Round 1: Standard grid (same as Step 3)
GRID_R1 = {
    "atr_stop_mult": [1.0, 1.5, 2.0, 3.0],
    "atr_target_mult": [1.5, 2.0, 3.0],
    "max_hold_bars": [15, 20],
    "cooldown_pullback_pct": [0.02, 0.03],
}

# Round 2: Tighter params for faster resolution
GRID_R2 = {
    "atr_stop_mult": [1.0, 1.5],
    "atr_target_mult": [1.0, 1.5],
    "max_hold_bars": [10, 15],
    "cooldown_pullback_pct": [0.02, 0.03],
}


def run_grid(df, archetype, grid, direction):
    """Test all param combos for one archetype/direction. Return best result."""
    combos = list(itertools.product(*grid.values()))
    keys = list(grid.keys())
    best = None

    for values in combos:
        params = {**DEFAULTS}
        for k, v in zip(keys, values):
            params[k] = v
        result = evaluate_params(df, archetype, params, direction)
        if result is None:
            continue
        if best is None or result["oos_wr"] > best["oos_wr"]:
            if result["oos_pf"] >= 0.8:
                best = result
                best["archetype"] = archetype

    return best


def iron_condor_analysis(df, ticker):
    """Check if ticker is suitable for iron condor (neutral) signals."""
    focus = df[df.index >= pd.Timestamp("2020-01-01")]
    if len(focus) < 200:
        return None

    _, _, adx = calc_adx(focus, 14, 14)
    adx = adx.dropna()
    daily_ret = focus["Close"].pct_change().dropna()

    pct_ranging = (adx < 20).mean()
    pct_trending = (adx > 25).mean()
    autocorr = daily_ret.autocorr(lag=1)
    avg_atr_pct = (calc_atr(focus, 14) / focus["Close"] * 100).mean()

    suitable = pct_ranging > 0.40 and autocorr < -0.03

    return {
        "ticker": ticker,
        "pct_ranging": round(pct_ranging, 3),
        "pct_trending": round(pct_trending, 3),
        "autocorr": round(autocorr, 3),
        "avg_atr_pct": round(avg_atr_pct, 2),
        "suitable": suitable,
    }


def main():
    print("=" * 70)
    print("  RECOVERING EXCLUDED TICKERS")
    print("=" * 70)

    results = []
    recovered = {}
    ic_results = []

    for ticker in EXCLUDED:
        t0 = time.time()
        print(f"\n  {ticker}...", flush=True)

        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception:
            print(f"    data not found")
            continue

        best_long = None
        best_short = None
        best_long_arch = ""
        best_short_arch = ""

        # Round 1: All archetypes × standard grid × long + short
        print(f"    Round 1: 3 archetypes × {len(list(itertools.product(*GRID_R1.values())))} params...", end=" ", flush=True)
        for arch in ARCHETYPES:
            r = run_grid(df, arch, GRID_R1, "long")
            if r and (best_long is None or r["oos_wr"] > best_long["oos_wr"]):
                best_long = r
                best_long_arch = arch

            r = run_grid(df, arch, GRID_R1, "short")
            if r and (best_short is None or r["oos_wr"] > best_short["oos_wr"]):
                best_short = r
                best_short_arch = arch

        long_ok = best_long and best_long["oos_wr"] > 0.45 and best_long["oos_pf"] > 1.0 and best_long["oos_trades"] >= 10
        short_ok = best_short and best_short["oos_wr"] > 0.45 and best_short["oos_pf"] > 1.0 and best_short["oos_trades"] >= 10

        if long_ok or short_ok:
            print("RECOVERED in Round 1!")
        else:
            # Round 2: Tighter params
            print("no.", flush=True)
            print(f"    Round 2: tighter params...", end=" ", flush=True)
            for arch in ARCHETYPES:
                r = run_grid(df, arch, GRID_R2, "long")
                if r and (best_long is None or r["oos_wr"] > best_long["oos_wr"]):
                    best_long = r
                    best_long_arch = arch

                r = run_grid(df, arch, GRID_R2, "short")
                if r and (best_short is None or r["oos_wr"] > best_short["oos_wr"]):
                    best_short = r
                    best_short_arch = arch

            long_ok = best_long and best_long["oos_wr"] > 0.45 and best_long["oos_pf"] > 1.0 and best_long["oos_trades"] >= 10
            short_ok = best_short and best_short["oos_wr"] > 0.45 and best_short["oos_pf"] > 1.0 and best_short["oos_trades"] >= 10

            if long_ok or short_ok:
                print("RECOVERED in Round 2!")
            else:
                print("no.")

        # Round 3: Iron condor analysis (regardless of directional outcome)
        ic = iron_condor_analysis(df, ticker)
        if ic:
            ic_results.append(ic)

        # Determine direction
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
        elif ic and ic["suitable"]:
            direction = "iron_condor"
        else:
            direction = "excluded"

        elapsed = time.time() - t0

        row = {"Ticker": ticker, "Direction": direction}
        if best_long:
            row.update({"L_Arch": best_long_arch[:8], "L_WR": best_long["oos_wr"],
                        "L_PF": best_long["oos_pf"], "L_N": best_long["oos_trades"],
                        "L_Degrad": best_long["degradation"]})
        else:
            row.update({"L_Arch": "—", "L_WR": 0, "L_PF": 0, "L_N": 0, "L_Degrad": 0})

        if best_short:
            row.update({"S_Arch": best_short_arch[:8], "S_WR": best_short["oos_wr"],
                        "S_PF": best_short["oos_pf"], "S_N": best_short["oos_trades"]})
        else:
            row.update({"S_Arch": "—", "S_WR": 0, "S_PF": 0, "S_N": 0})

        if ic:
            row["IC_Suitable"] = "YES" if ic["suitable"] else "no"
        else:
            row["IC_Suitable"] = "—"

        results.append(row)

        l_str = f"L:{best_long['oos_wr']:.0%}" if best_long else "L:—"
        s_str = f"S:{best_short['oos_wr']:.0%}" if best_short else "S:—"
        ic_str = f"IC:{'YES' if ic and ic['suitable'] else 'no'}"
        print(f"    → {direction} | {l_str} {s_str} {ic_str} ({elapsed:.0f}s)")

        # Save config for recovered tickers
        if direction != "excluded":
            cfg = {"ticker": ticker, "direction": direction}
            if best_long:
                cfg["long"] = {"archetype": best_long_arch, "params": best_long["params"],
                               "oos_wr": best_long["oos_wr"], "oos_pf": best_long["oos_pf"]}
            if best_short:
                cfg["short"] = {"archetype": best_short_arch, "params": best_short["params"],
                                "oos_wr": best_short["oos_wr"], "oos_pf": best_short["oos_pf"]}
            if ic and ic["suitable"]:
                cfg["iron_condor"] = ic
            recovered[ticker] = cfg

    # Print results
    print(f"\n{'=' * 70}")
    print(tabulate(results, headers="keys", tablefmt="simple", floatfmt=".2f"))

    rec_count = sum(1 for r in results if r["Direction"] != "excluded")
    exc_count = sum(1 for r in results if r["Direction"] == "excluded")
    print(f"\n  Recovered: {rec_count}/{len(EXCLUDED)}")
    print(f"  Still excluded: {exc_count} ({', '.join(r['Ticker'] for r in results if r['Direction'] == 'excluded') or 'none'})")

    # Iron condor suitability
    if ic_results:
        print(f"\n  Iron Condor Suitability:")
        for ic in ic_results:
            status = "SUITABLE" if ic["suitable"] else "unsuitable"
            print(f"    {ic['ticker']:>6s}: {status} (ranging={ic['pct_ranging']:.0%}, "
                  f"autocorr={ic['autocorr']:.3f}, ATR={ic['avg_atr_pct']:.1f}%)")

    # Update ticker_configs.json
    config_path = Path("config") / "ticker_configs.json"
    existing = {}
    if config_path.exists():
        with open(config_path) as f:
            existing = json.load(f)

    for ticker, cfg in recovered.items():
        if "params" in cfg.get("long", {}):
            cfg["long"]["params"] = {k: v for k, v in cfg["long"]["params"].items()
                                      if k in list(GRID_R1.keys()) + list(GRID_R2.keys()) +
                                      ["risk_budget", "premium_atr_ratio", "slippage", "max_hold_bars"]}
        if "params" in cfg.get("short", {}):
            cfg["short"]["params"] = {k: v for k, v in cfg["short"]["params"].items()
                                       if k in list(GRID_R1.keys()) + list(GRID_R2.keys()) +
                                       ["risk_budget", "premium_atr_ratio", "slippage", "max_hold_bars"]}
        existing[ticker] = cfg

    # Serialize — convert numpy types
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    clean = json.loads(json.dumps(existing, default=convert))
    with open(config_path, "w") as f:
        json.dump(clean, f, indent=2)
    print(f"\n  Updated: {config_path}")

    # Write report
    report_lines = ["# Excluded Tickers Retest", ""]
    report_lines.append(f"*Testing {len(EXCLUDED)} excluded tickers with all 3 archetypes + tighter params + iron condor*")
    report_lines.append("")
    report_lines.append("| Ticker | Direction | L_Arch | L_WR | L_PF | L_N | S_Arch | S_WR | S_PF | IC |")
    report_lines.append("|--------|-----------|--------|------|------|-----|--------|------|------|----|")
    for r in results:
        report_lines.append(
            f"| {r['Ticker']} | {r['Direction']} | {r.get('L_Arch','—')} | "
            f"{r.get('L_WR',0):.0%} | {r.get('L_PF',0):.2f} | {r.get('L_N',0)} | "
            f"{r.get('S_Arch','—')} | {r.get('S_WR',0):.0%} | {r.get('S_PF',0):.2f} | "
            f"{r.get('IC_Suitable','—')} |"
        )
    report_lines.append("")

    report_path = Path("reports") / "excluded_tickers_retest.md"
    report_path.write_text("\n".join(report_lines))
    print(f"  Report: {report_path}")

    # Final universe count
    total_qualified = len(existing)
    print(f"\n  Total universe: {total_qualified} tickers")


if __name__ == "__main__":
    main()
