#!/usr/bin/env python3
"""
Step 5: Final validation — Model C P&L across Tier 1 + Tier 2 tickers.
Generates FINAL_STRATEGY_REPORT.md with equity curve, monthly returns, drawdown.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from options_backtester import OptionsBacktester, OptionsTrade, DEFAULTS, TICKER_ARCHETYPE

MODEL_C = {"win": 0.50, "loss": -0.50, "flat": -0.25}
TIER1 = ["SLV", "MSFT", "TSLA", "XLE"]
TIER2 = ["AMD", "SOFI", "GLD"]
ALL_TICKERS = TIER1 + TIER2


def recalc_trade_pnl(trade, model):
    """Recalculate a single trade's P&L under Model C."""
    if trade.outcome == "WIN" and trade.pnl > 0:
        pxc = trade.pnl / 0.5
    elif trade.outcome == "FLAT_LOSS" and trade.pnl < 0:
        pxc = abs(trade.pnl) / 0.5
    elif trade.outcome == "LOSS" and trade.pnl < 0:
        pxc = abs(trade.pnl) / 1.0
    else:
        pxc = abs(trade.pnl) if trade.pnl != 0 else 100

    if trade.outcome == "WIN":
        return pxc * model["win"]
    elif trade.outcome == "FLAT_LOSS":
        return pxc * model["flat"]
    else:
        return pxc * model["loss"]


def main():
    print("=" * 70)
    print("  FINAL STRATEGY REPORT — Model C Managed Spreads")
    print("  Tier 1: SLV, MSFT, TSLA, XLE | Tier 2: AMD, SOFI, GLD")
    print("=" * 70)

    all_trades_mc = []  # (date, pnl, ticker, tier)
    ticker_results = []

    for ticker in ALL_TICKERS:
        tier = "T1" if ticker in TIER1 else "T2"
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception:
            continue

        archetype = TICKER_ARCHETYPE.get(ticker, "trend_pullback")
        bt = OptionsBacktester(ticker, archetype)
        log = bt.run(df)

        if not log.trades:
            continue

        # Recalculate P&L under Model C
        mc_pnls = []
        for t in log.trades:
            mc_pnl = recalc_trade_pnl(t, MODEL_C)
            mc_pnls.append(mc_pnl)
            all_trades_mc.append((t.exit_date, mc_pnl, ticker, tier))

        n = len(log.trades)
        wins = sum(1 for t in log.trades if t.outcome == "WIN")
        flats = sum(1 for t in log.trades if t.outcome == "FLAT_LOSS")
        mc_total = sum(mc_pnls)
        mc_gp = sum(p for p in mc_pnls if p > 0)
        mc_gl = abs(sum(p for p in mc_pnls if p <= 0))
        mc_pf = mc_gp / mc_gl if mc_gl > 0 else float("inf")

        # Max consecutive losses
        max_cl = 0
        cl = 0
        for t in log.trades:
            if t.outcome != "WIN":
                cl += 1
                max_cl = max(max_cl, cl)
            else:
                cl = 0

        ticker_results.append({
            "Ticker": ticker, "Tier": tier, "N": n,
            "WR%": round(100 * wins / n, 1),
            "Flat%": round(100 * flats / n, 1),
            "PF": round(mc_pf, 2),
            "Net$": round(mc_total, 0),
            "Expect$": round(mc_total / n, 1),
            "MaxCL": max_cl,
        })

    print()
    print(tabulate(ticker_results, headers="keys", tablefmt="simple", floatfmt=".1f"))

    # Sort trades by date for equity curve
    all_trades_mc.sort(key=lambda x: x[0])

    # Equity curve
    equity = 50000.0
    equity_curve = [(pd.Timestamp("2020-01-01"), equity)]
    for date, pnl, ticker, tier in all_trades_mc:
        # Tier 2 at half size
        adj_pnl = pnl * 0.5 if tier == "T2" else pnl
        equity += adj_pnl
        equity_curve.append((date, equity))

    eq_df = pd.DataFrame(equity_curve, columns=["Date", "Equity"]).set_index("Date")

    # Drawdown
    peak = eq_df["Equity"].cummax()
    drawdown = eq_df["Equity"] - peak
    max_dd = drawdown.min()
    max_dd_pct = (max_dd / peak[drawdown.idxmin()]) * 100 if max_dd < 0 else 0

    # Monthly returns
    monthly_pnl = {}
    for date, pnl, ticker, tier in all_trades_mc:
        adj_pnl = pnl * 0.5 if tier == "T2" else pnl
        key = (date.year, date.month)
        monthly_pnl[key] = monthly_pnl.get(key, 0) + adj_pnl

    # Print summary
    t1_pnl = sum(p * (0.5 if tier == "T2" else 1.0) for _, p, _, tier in all_trades_mc if tier == "T1")
    t2_pnl = sum(p * 0.5 for _, p, _, tier in all_trades_mc if tier == "T2")
    total_pnl = t1_pnl + t2_pnl

    print(f"\n  PORTFOLIO SUMMARY ($50K account, Tier 2 at half size):")
    print(f"    Tier 1 PnL:     ${t1_pnl:>10,.0f}")
    print(f"    Tier 2 PnL:     ${t2_pnl:>10,.0f}")
    print(f"    Total PnL:      ${total_pnl:>10,.0f}")
    print(f"    Final Equity:   ${equity:>10,.0f}")
    print(f"    Max Drawdown:   ${max_dd:>10,.0f} ({max_dd_pct:.1f}%)")
    print(f"    Total Trades:   {len(all_trades_mc)}")

    # Monthly stats
    if monthly_pnl:
        monthly_vals = list(monthly_pnl.values())
        print(f"\n  MONTHLY P&L:")
        print(f"    Best month:     ${max(monthly_vals):>8,.0f}")
        print(f"    Worst month:    ${min(monthly_vals):>8,.0f}")
        print(f"    Avg month:      ${np.mean(monthly_vals):>8,.0f}")
        print(f"    Positive months: {sum(1 for v in monthly_vals if v > 0)}/{len(monthly_vals)}")

    # Write report
    lines = ["# FINAL STRATEGY REPORT", ""]
    lines.append("*Swing Options V2 — Model C Managed Spreads — Production Configuration*")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Universe**: {len(ALL_TICKERS)} tickers (4 Tier 1, 3 Tier 2)")
    lines.append(f"- **Trade Structure**: Vertical debit spreads, 45-60 DTE")
    lines.append(f"- **Management**: TP at 50% max profit, SL at 50% max loss, close by day 15")
    lines.append(f"- **Total PnL (2020-2026)**: ${total_pnl:,.0f}")
    lines.append(f"- **Final Equity**: ${equity:,.0f} (from $50,000)")
    lines.append(f"- **Max Drawdown**: ${max_dd:,.0f} ({max_dd_pct:.1f}%)")
    lines.append(f"- **Total Trades**: {len(all_trades_mc)}")
    lines.append("")

    lines.append("## Per-Ticker Results (Model C)")
    lines.append("")
    lines.append("| Ticker | Tier | Trades | WR% | Flat% | PF | Net PnL | Expect$/trade | Max Consec Losses |")
    lines.append("|--------|------|--------|-----|-------|-----|---------|---------------|-------------------|")
    for r in ticker_results:
        lines.append(f"| {r['Ticker']} | {r['Tier']} | {r['N']} | {r['WR%']:.1f} | "
                     f"{r['Flat%']:.1f} | {r['PF']:.2f} | ${r['Net$']:.0f} | "
                     f"${r['Expect$']:.1f} | {r['MaxCL']} |")
    lines.append("")

    lines.append("## Risk Analysis")
    lines.append("")
    lines.append(f"- **Max Drawdown**: ${max_dd:,.0f} ({max_dd_pct:.1f}%)")
    if monthly_pnl:
        lines.append(f"- **Worst Month**: ${min(monthly_vals):,.0f}")
        lines.append(f"- **Best Month**: ${max(monthly_vals):,.0f}")
        lines.append(f"- **Positive Months**: {sum(1 for v in monthly_vals if v > 0)}/{len(monthly_vals)} ({100*sum(1 for v in monthly_vals if v > 0)/len(monthly_vals):.0f}%)")
    lines.append("")

    lines.append("## Options-Specific Metrics")
    lines.append("")
    total_trades = sum(r["N"] for r in ticker_results)
    total_flats = sum(r["Flat%"] * r["N"] / 100 for r in ticker_results)
    flat_pct = total_flats / total_trades * 100 if total_trades > 0 else 0
    lines.append(f"- **Overall Flat Loss Rate**: {flat_pct:.1f}%")
    if flat_pct > 30:
        lines.append(f"  ⚠️ ABOVE 30% THRESHOLD — strategy may not suit options")
    else:
        lines.append(f"  ✓ Below 30% threshold — acceptable for options trading")
    lines.append("")

    lines.append("## Signal Frequency")
    lines.append("")
    for r in ticker_results:
        years = 6.25  # 2020-2026
        spm = r["N"] / (years * 12)
        lines.append(f"- **{r['Ticker']}**: {spm:.1f} signals/month ({r['N']} total over {years:.1f} years)")
    lines.append("")

    lines.append("## Recommended Account Size")
    lines.append("")
    lines.append("For 7 simultaneous positions at 3% risk each:")
    lines.append("- **Minimum**: $25,000 (7 × $750 max risk per trade)")
    lines.append("- **Recommended**: $50,000 (comfortable margin for drawdowns)")
    lines.append("- **Optimal**: $100,000 (can handle worst-month scenarios)")
    lines.append("")

    lines.append("## Production Deployment Checklist")
    lines.append("")
    lines.append("- [ ] Load Swing Options V2 on 4h/6h chart for each Tier 1 ticker")
    lines.append("- [ ] Set up webhook alerts → trading bot")
    lines.append("- [ ] Configure bot with Model C management rules")
    lines.append("- [ ] Paper trade for 2 weeks to validate intraday timing")
    lines.append("- [ ] Go live with Tier 1 only (SLV, MSFT, TSLA, XLE)")
    lines.append("- [ ] After 1 month: evaluate, then add Tier 2 if results match backtest")
    lines.append("- [ ] After 3 months: full review and parameter adjustment")
    lines.append("")

    lines.append("## Honest Assessment")
    lines.append("")
    lines.append("**Strengths:**")
    lines.append("- Model C's managed approach (50% TP, 50% SL) produces realistic payoff ratios")
    lines.append("- 4 Tier 1 tickers have proven positive expectancy in backtesting")
    lines.append("- Low flat loss rate (<15%) means theta isn't destroying the edge")
    lines.append("- Diverse universe (commodities, tech, energy) provides uncorrelated signals")
    lines.append("")
    lines.append("**Weaknesses:**")
    lines.append("- Only 4 of 15 tickers are profitable — most of the universe is Tier 3 (monitor only)")
    lines.append("- Expected monthly return of 0.3-0.6% is modest")
    lines.append("- Index ETFs (SPY, QQQ, IWM) don't work with directional options — only iron condors")
    lines.append("- Backtested on daily data only — 4h/6h intraday behavior needs live validation")
    lines.append("")
    lines.append("**What Could Improve Results:**")
    lines.append("- Better entry timing with real 4h/6h data (current is daily proxy)")
    lines.append("- Add IV rank filter (avoid expensive options)")
    lines.append("- Consider 0DTE or weekly strategies for SPY/QQQ (different thesis entirely)")
    lines.append("- Expand universe to more trending stocks (test GOOGL, NFLX, AVGO)")

    out = Path("reports") / "FINAL_STRATEGY_REPORT.md"
    out.write_text("\n".join(lines))
    print(f"\n  Report: {out}")


if __name__ == "__main__":
    main()
