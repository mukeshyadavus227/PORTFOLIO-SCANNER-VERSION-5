#!/usr/bin/env python3
"""
Options structure comparison: 3 realistic trade models across 15 tickers.

Model A — Vertical Spreads: WIN +65%, LOSS -100%, FLAT -40%  (BE ~55%)
Model B — ITM Options:      WIN +75%, LOSS -100%, FLAT -30%  (BE ~57%)
Model C — Managed Spreads:  WIN +50%, LOSS -50%,  FLAT -25%  (BE ~43%)
Current — Naked ATM:        WIN +50%, LOSS -100%, FLAT -50%  (BE ~67%)

Also tests conviction filter (proxy: tighter RSI gate for signal quality).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from options_backtester import (
    OptionsBacktester, OptionsTrade, OptionsTradeLog, DEFAULTS, TICKER_ARCHETYPE,
)

TICKERS = ["SPY", "QQQ", "IWM", "SLV", "GLD", "XLE", "XLF",
           "NVDA", "TSLA", "AMD", "MSFT", "META", "AMZN", "SOFI", "INTC"]

MODELS = {
    "Current": {"win": 0.50, "loss": -1.00, "flat": -0.50, "be_wr": 67},
    "A_Spread": {"win": 0.65, "loss": -1.00, "flat": -0.40, "be_wr": 55},
    "B_ITM": {"win": 0.75, "loss": -1.00, "flat": -0.30, "be_wr": 57},
    "C_Managed": {"win": 0.50, "loss": -0.50, "flat": -0.25, "be_wr": 43},
}


def recalculate_pnl(trades, model):
    """Recalculate P&L for a list of trades under a different model."""
    total_pnl = 0.0
    for t in trades:
        # Estimate the premium from the original trade
        # Original: WIN = +0.5*prem*contracts, so prem*contracts = pnl/0.5 for wins
        # We need to reverse-engineer the premium per contract
        if t.outcome == "WIN" and t.pnl > 0:
            prem_x_contracts = t.pnl / 0.5  # original model: win = +50%
        elif t.outcome == "FLAT_LOSS" and t.pnl < 0:
            prem_x_contracts = abs(t.pnl) / 0.5  # original: flat = -50%
        elif t.outcome == "LOSS" and t.pnl < 0:
            prem_x_contracts = abs(t.pnl) / 1.0  # original: loss = -100%
        else:
            prem_x_contracts = abs(t.pnl) if t.pnl != 0 else 100  # fallback

        # Apply new model
        if t.outcome == "WIN":
            new_pnl = prem_x_contracts * model["win"]
        elif t.outcome == "FLAT_LOSS":
            new_pnl = prem_x_contracts * model["flat"]
        else:
            new_pnl = prem_x_contracts * model["loss"]

        total_pnl += new_pnl

    return total_pnl


def summarize_model(trades, model):
    """Compute metrics under a specific P&L model."""
    if not trades:
        return {"n": 0, "wr": 0, "pf": 0, "pnl": 0, "expect": 0, "flat%": 0}

    n = len(trades)
    wins = sum(1 for t in trades if t.outcome == "WIN")
    flats = sum(1 for t in trades if t.outcome == "FLAT_LOSS")
    wr = 100 * wins / n

    total_pnl = recalculate_pnl(trades, model)

    # Compute PF under new model
    gp = 0.0
    gl = 0.0
    for t in trades:
        if t.outcome == "WIN" and t.pnl > 0:
            pxc = t.pnl / 0.5
        elif t.outcome == "FLAT_LOSS" and t.pnl < 0:
            pxc = abs(t.pnl) / 0.5
        elif t.outcome == "LOSS" and t.pnl < 0:
            pxc = abs(t.pnl) / 1.0
        else:
            pxc = abs(t.pnl) if t.pnl != 0 else 100

        if t.outcome == "WIN":
            gp += pxc * model["win"]
        else:
            gl += abs(pxc * (model["flat"] if t.outcome == "FLAT_LOSS" else model["loss"]))

    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)

    return {
        "n": n, "wr": round(wr, 1), "flat%": round(100 * flats / n, 1),
        "pf": round(pf, 2), "pnl": round(total_pnl, 0),
        "expect": round(total_pnl / n, 1),
        "profitable": total_pnl > 0,
    }


def main():
    print("=" * 70)
    print("  OPTIONS STRUCTURE COMPARISON")
    print("  4 P&L models × 15 tickers + conviction filter")
    print("=" * 70)

    # Collect all trades per ticker
    ticker_trades = {}
    ticker_trades_hq = {}  # high-quality filter (proxy: use tighter archetype)

    for ticker in TICKERS:
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception:
            continue

        archetype = TICKER_ARCHETYPE.get(ticker, "trend_pullback")

        # Standard backtest
        bt = OptionsBacktester(ticker, archetype)
        log = bt.run(df)
        ticker_trades[ticker] = log.trades

        # High-conviction proxy: tighter stops (1.5x ATR stop, 1.5x target)
        # This forces faster resolution → fewer flat losses
        params_hq = {**DEFAULTS, "atr_stop_mult": 1.5, "atr_target_mult": 1.5, "max_hold_bars": 15}
        bt_hq = OptionsBacktester(ticker, archetype, params_hq)
        log_hq = bt_hq.run(df)
        ticker_trades_hq[ticker] = log_hq.trades

    # ── Results tables ──
    for label, trades_dict in [("ALL SIGNALS", ticker_trades), ("HIGH CONVICTION (tight stops)", ticker_trades_hq)]:
        print(f"\n{'=' * 70}")
        print(f"  {label}")
        print(f"{'=' * 70}")

        rows = []
        model_profitable = {m: 0 for m in MODELS}
        model_total_pnl = {m: 0.0 for m in MODELS}

        for ticker in TICKERS:
            if ticker not in trades_dict or not trades_dict[ticker]:
                continue
            trades = trades_dict[ticker]

            row = {"Ticker": ticker, "N": len(trades)}
            wr = 100 * sum(1 for t in trades if t.outcome == "WIN") / len(trades)
            row["WR%"] = round(wr, 0)

            for model_name, model in MODELS.items():
                s = summarize_model(trades, model)
                short_name = model_name[:7]
                row[f"{short_name}_PF"] = s["pf"]
                row[f"{short_name}_PnL"] = s["pnl"]
                row[f"{short_name}_OK"] = "YES" if s["profitable"] else "no"

                if s["profitable"]:
                    model_profitable[model_name] += 1
                model_total_pnl[model_name] += s["pnl"]

            rows.append(row)

        print()
        print(tabulate(rows, headers="keys", tablefmt="simple", floatfmt=".1f"))

        # Summary
        print(f"\n  PROFITABLE TICKERS BY MODEL:")
        for model_name in MODELS:
            count = model_profitable[model_name]
            total = model_total_pnl[model_name]
            be = MODELS[model_name]["be_wr"]
            print(f"    {model_name:<12s}: {count:>2d}/15 profitable  "
                  f"${total:>12,.0f} total PnL  (breakeven WR: {be}%)")

    # ── Per-ticker recommendations ──
    print(f"\n{'=' * 70}")
    print("  RECOMMENDED MODEL PER TICKER")
    print(f"{'=' * 70}")

    recs = []
    for ticker in TICKERS:
        if ticker not in ticker_trades or not ticker_trades[ticker]:
            continue
        trades = ticker_trades[ticker]
        wr = 100 * sum(1 for t in trades if t.outcome == "WIN") / len(trades)

        # Find best model (highest PnL)
        best_model = ""
        best_pnl = float("-inf")
        for model_name, model in MODELS.items():
            s = summarize_model(trades, model)
            if s["pnl"] > best_pnl:
                best_pnl = s["pnl"]
                best_model = model_name

        profitable = best_pnl > 0
        recs.append({
            "Ticker": ticker, "WR": round(wr, 0),
            "Best_Model": best_model,
            "Best_PnL": round(best_pnl, 0),
            "Profitable": "YES" if profitable else "no",
            "Note": "Model C recommended" if wr >= 43 and not profitable else "",
        })

    print()
    print(tabulate(recs, headers="keys", tablefmt="simple", floatfmt=".0f"))

    # ── Write report ──
    lines = ["# Options Structure Comparison", ""]
    lines.append("*4 P&L models tested across 15 tickers with options swing backtester*")
    lines.append("")
    lines.append("## Models Tested")
    lines.append("")
    lines.append("| Model | WIN | LOSS | FLAT | Breakeven WR |")
    lines.append("|-------|-----|------|------|-------------|")
    for name, m in MODELS.items():
        lines.append(f"| {name} | {m['win']:+.0%} | {m['loss']:+.0%} | {m['flat']:+.0%} | {m['be_wr']}% |")
    lines.append("")

    lines.append("## Results — All Signals")
    lines.append("")
    lines.append("| Ticker | N | WR | Cur PF | Cur PnL | A PF | A PnL | B PF | B PnL | C PF | C PnL |")
    lines.append("|--------|---|-----|--------|---------|------|-------|------|-------|------|-------|")
    for ticker in TICKERS:
        if ticker not in ticker_trades or not ticker_trades[ticker]:
            continue
        trades = ticker_trades[ticker]
        n = len(trades)
        wr = 100 * sum(1 for t in trades if t.outcome == "WIN") / n
        cur = summarize_model(trades, MODELS["Current"])
        a = summarize_model(trades, MODELS["A_Spread"])
        b = summarize_model(trades, MODELS["B_ITM"])
        c = summarize_model(trades, MODELS["C_Managed"])
        lines.append(f"| {ticker} | {n} | {wr:.0f}% | {cur['pf']:.2f} | ${cur['pnl']:.0f} | "
                     f"{a['pf']:.2f} | ${a['pnl']:.0f} | {b['pf']:.2f} | ${b['pnl']:.0f} | "
                     f"{c['pf']:.2f} | ${c['pnl']:.0f} |")
    lines.append("")

    lines.append("## Profitable Tickers by Model")
    lines.append("")
    for name in MODELS:
        count = sum(1 for ticker in TICKERS if ticker in ticker_trades and ticker_trades[ticker] and
                    summarize_model(ticker_trades[ticker], MODELS[name])["profitable"])
        lines.append(f"- **{name}**: {count}/15 profitable")
    lines.append("")

    lines.append("## Per-Ticker Recommendations")
    lines.append("")
    lines.append("| Ticker | WR | Best Model | Best PnL | Profitable |")
    lines.append("|--------|-----|-----------|----------|------------|")
    for r in recs:
        lines.append(f"| {r['Ticker']} | {r['WR']:.0f}% | {r['Best_Model']} | ${r['Best_PnL']:.0f} | {r['Profitable']} |")

    out = Path("reports") / "options_structure_comparison.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"\n  Report: {out}")


if __name__ == "__main__":
    main()
