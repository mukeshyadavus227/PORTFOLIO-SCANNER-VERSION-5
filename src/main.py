#!/usr/bin/env python3
"""
Portfolio Scanner V5 — Full Backtesting Pipeline

Usage:
    python src/main.py                           # all tickers, full range
    python src/main.py --tickers SPY QQQ AAPL    # specific tickers
    python src/main.py --start-date 2020-01-01   # date filter
    python src/main.py --end-date 2024-12-31     # date filter
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_all_data
from scorer import run_full_pipeline
from simulator import TradeSimulator, INSTRUMENT_PRESETS
from reporter import (
    calculate_metrics,
    per_strategy_breakdown,
    per_regime_breakdown,
    generate_report,
    recommend_changes,
    print_report_summary,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Portfolio Scanner V5 Backtester")
    p.add_argument("--tickers", nargs="+", default=None,
                   help="Tickers to backtest (default: all in data/)")
    p.add_argument("--start-date", type=str, default=None,
                   help="Start date filter (YYYY-MM-DD)")
    p.add_argument("--end-date", type=str, default=None,
                   help="End date filter (YYYY-MM-DD)")
    p.add_argument("--data-dir", type=str, default="data/",
                   help="Directory containing data files")
    p.add_argument("--report-dir", type=str, default="reports/",
                   help="Output directory for reports")
    p.add_argument("--capital", type=float, default=10_000.0,
                   help="Initial capital ($)")
    p.add_argument("--min-composite", type=float, default=50.0,
                   help="Minimum composite score to fire signal")
    return p.parse_args()


def run_ticker(ticker: str, df: pd.DataFrame, args: argparse.Namespace,
               ) -> dict | None:
    """Run the full pipeline for a single ticker. Returns metrics dict."""
    # Date filter
    if args.start_date:
        df = df[df.index >= pd.Timestamp(args.start_date)]
    if args.end_date:
        df = df[df.index <= pd.Timestamp(args.end_date)]

    if len(df) < 250:
        print(f"  {ticker}: Skipping — only {len(df)} bars (need >= 250)")
        return None

    t0 = time.time()

    # Scoring pipeline
    signals, meta = run_full_pipeline(df, min_composite=args.min_composite,
                                      expiry_bars=3)

    # Simulator
    sim = TradeSimulator.from_preset(ticker, initial_capital=args.capital)
    trade_log = sim.simulate(df, signals, meta)

    elapsed = time.time() - t0

    # Metrics
    metrics = calculate_metrics(trade_log)
    strat_df = per_strategy_breakdown(trade_log)
    regime_df = per_regime_breakdown(trade_log)
    recs = recommend_changes(metrics, strat_df, regime_df)

    # Generate report files
    report_path = generate_report(trade_log, ticker, args.report_dir)

    # Console summary
    print_report_summary(ticker, metrics, strat_df, regime_df, recs)
    print(f"\n  Report saved: {report_path}/  ({elapsed:.1f}s)")

    return metrics


def main() -> None:
    args = parse_args()

    print("=" * 65)
    print("  PORTFOLIO SCANNER V5 — BACKTESTER")
    print("=" * 65)

    # Load data
    all_data = load_all_data(args.data_dir)
    if not all_data:
        print("No data files found. Exiting.")
        sys.exit(1)

    # Filter tickers
    if args.tickers:
        tickers = [t for t in args.tickers if t in all_data]
        missing = [t for t in args.tickers if t not in all_data]
        if missing:
            print(f"  Warning: tickers not found in data: {missing}")
    else:
        tickers = sorted(all_data.keys())

    print(f"  Tickers: {len(tickers)}  |  Data dir: {args.data_dir}")
    if args.start_date:
        print(f"  Start: {args.start_date}")
    if args.end_date:
        print(f"  End: {args.end_date}")
    print()

    # Run each ticker
    all_metrics = {}
    for ticker in tickers:
        df = all_data[ticker]
        result = run_ticker(ticker, df, args)
        if result:
            all_metrics[ticker] = result

    # ── Cross-ticker summary ──
    if len(all_metrics) > 1:
        print(f"\n{'=' * 65}")
        print(f"  CROSS-TICKER SUMMARY ({len(all_metrics)} tickers)")
        print(f"{'=' * 65}")

        rows = []
        for ticker, m in sorted(all_metrics.items()):
            rows.append({
                "Ticker": ticker,
                "Trades": m.get("total_trades", 0),
                "WR%": m.get("win_rate", 0),
                "PF": m.get("profit_factor", 0),
                "Net PnL": m.get("net_pnl", 0),
                "Sharpe": m.get("sharpe_ratio", 0),
                "MaxDD$": m.get("max_drawdown_dollar", 0),
                "Expect$": m.get("expectancy", 0),
            })
        print(tabulate(rows, headers="keys", tablefmt="simple", floatfmt=".2f"))

        # Aggregate
        total_trades = sum(m.get("total_trades", 0) for m in all_metrics.values())
        total_pnl = sum(m.get("net_pnl", 0) for m in all_metrics.values())
        avg_wr = sum(m.get("win_rate", 0) for m in all_metrics.values()) / len(all_metrics)
        avg_pf = [m.get("profit_factor", 0) for m in all_metrics.values()
                  if m.get("profit_factor", 0) != float("inf")]
        avg_pf_val = sum(avg_pf) / len(avg_pf) if avg_pf else 0

        print(f"\n  Portfolio total: {total_trades} trades, "
              f"${total_pnl:.2f} net PnL, "
              f"{avg_wr:.1f}% avg WR, "
              f"{avg_pf_val:.2f} avg PF")


if __name__ == "__main__":
    main()
