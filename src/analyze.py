#!/usr/bin/env python3
"""
Deep analysis of backtest results — identifies what actually works
across strategies, regimes, composite scores, and holding periods.

Read-only: does NOT modify any strategy code.
Output:  reports/strategy_analysis.md
"""

import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import load_all_data
from scorer import run_full_pipeline
from simulator import TradeSimulator
from reporter import calculate_metrics


# ═══════════════════════════════════════════════════════════════════════════
# Run pipeline, collect all trades
# ═══════════════════════════════════════════════════════════════════════════

def collect_all_trades() -> tuple[pd.DataFrame, dict]:
    """Run pipeline on all tickers and collect trade-level data."""
    all_data = load_all_data("data/")
    all_trades = []
    ticker_meta = {}  # ticker -> (df, meta, log)

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
        tdf["Ticker"] = ticker
        tdf["Holding Days"] = (tdf["Exit Date"] - tdf["Entry Date"]).dt.days
        all_trades.append(tdf)
        ticker_meta[ticker] = (df, meta, log)

    trades = pd.concat(all_trades, ignore_index=True)
    trades["Winner"] = trades["PnL"] > 0
    return trades, ticker_meta


# ═══════════════════════════════════════════════════════════════════════════
# Analysis 1: Profitable ticker deep dive
# ═══════════════════════════════════════════════════════════════════════════

PROFITABLE_TICKERS = ["INTC", "SPY", "AMD", "AMZN", "EWW"]


def analyze_profitable(trades: pd.DataFrame) -> list[str]:
    """Deep dive on the 5 most profitable tickers."""
    lines = []
    lines.append("## 1. Profitable Ticker Deep Dive")
    lines.append("")

    for ticker in PROFITABLE_TICKERS:
        t = trades[trades["Ticker"] == ticker]
        if t.empty:
            continue
        wins = t[t["Winner"]]
        losses = t[~t["Winner"]]

        lines.append(f"### {ticker} ({len(t)} trades, ${t['PnL'].sum():.2f} net)")
        lines.append("")

        # Strategy breakdown
        lines.append("**Strategy P&L:**")
        lines.append("")
        lines.append("| Strategy | Trades | WR% | Net PnL | Avg Win | Avg Loss | Expectancy |")
        lines.append("|----------|--------|-----|---------|---------|----------|------------|")
        for strat in sorted(t["Strategy"].unique()):
            s = t[t["Strategy"] == strat]
            sw = s[s["Winner"]]
            sl = s[~s["Winner"]]
            wr = 100 * len(sw) / len(s) if len(s) else 0
            avg_w = sw["PnL"].mean() if len(sw) else 0
            avg_l = sl["PnL"].mean() if len(sl) else 0
            exp = wr / 100 * avg_w + (1 - wr / 100) * avg_l
            lines.append(f"| {strat} | {len(s)} | {wr:.1f} | ${s['PnL'].sum():.2f} | "
                         f"${avg_w:.2f} | ${avg_l:.2f} | ${exp:.2f} |")
        lines.append("")

        # Regime breakdown
        lines.append("**Regime breakdown (winners vs losers):**")
        lines.append("")
        lines.append("| Regime | Trades | Wins | Losses | WR% | Net PnL |")
        lines.append("|--------|--------|------|--------|-----|---------|")
        for regime in sorted(t["Regime"].unique()):
            r = t[t["Regime"] == regime]
            rw = r[r["Winner"]]
            rl = r[~r["Winner"]]
            wr = 100 * len(rw) / len(r) if len(r) else 0
            lines.append(f"| {regime} | {len(r)} | {len(rw)} | {len(rl)} | "
                         f"{wr:.1f} | ${r['PnL'].sum():.2f} |")
        lines.append("")

        # Composite score: winners vs losers
        avg_score_w = wins["Score"].mean() if len(wins) else 0
        avg_score_l = losses["Score"].mean() if len(losses) else 0
        lines.append(f"**Composite score:** Winners avg = {avg_score_w:.1f}, "
                     f"Losers avg = {avg_score_l:.1f}, "
                     f"Delta = {avg_score_w - avg_score_l:+.1f}")
        lines.append("")

        # Holding period
        avg_hold_w = wins["Holding Days"].mean() if len(wins) else 0
        avg_hold_l = losses["Holding Days"].mean() if len(losses) else 0
        lines.append(f"**Holding period:** Winners avg = {avg_hold_w:.1f} days, "
                     f"Losers avg = {avg_hold_l:.1f} days")
        lines.append("")

        # Composite score threshold for 50% WR
        threshold_50 = find_wr_threshold(t, 50.0)
        lines.append(f"**50% WR threshold:** Composite score >= {threshold_50}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return lines


def find_wr_threshold(trades: pd.DataFrame, target_wr: float) -> str:
    """Find the composite score threshold where WR exceeds target."""
    for thresh in range(50, 100, 5):
        subset = trades[trades["Score"] >= thresh]
        if len(subset) < 3:
            continue
        wr = 100 * subset["Winner"].mean()
        if wr >= target_wr:
            return f"{thresh} (WR={wr:.1f}% on {len(subset)} trades)"
    return "not reached (insufficient high-score trades)"


# ═══════════════════════════════════════════════════════════════════════════
# Analysis 2: Losing ticker salvage
# ═══════════════════════════════════════════════════════════════════════════

def analyze_losers(trades: pd.DataFrame) -> list[str]:
    """Find profitable pockets within losing tickers."""
    lines = []
    lines.append("## 2. Losing Ticker Salvage")
    lines.append("")

    losing_tickers = []
    for ticker in sorted(trades["Ticker"].unique()):
        t = trades[trades["Ticker"] == ticker]
        if t["PnL"].sum() < 0 and len(t) >= 10:
            losing_tickers.append(ticker)

    # Regime pockets: which regime was profitable on losing tickers?
    lines.append("### Profitable Regime Pockets (on losing tickers)")
    lines.append("")
    lines.append("| Ticker | Regime | Trades | WR% | Net PnL | Note |")
    lines.append("|--------|--------|--------|-----|---------|------|")

    regime_pockets = []
    for ticker in losing_tickers:
        t = trades[trades["Ticker"] == ticker]
        for regime in sorted(t["Regime"].unique()):
            r = t[t["Regime"] == regime]
            if len(r) < 3:
                continue
            pnl = r["PnL"].sum()
            wr = 100 * r["Winner"].mean()
            if pnl > 0:
                regime_pockets.append((ticker, regime, len(r), wr, pnl))
                lines.append(f"| {ticker} | {regime} | {len(r)} | {wr:.1f} | "
                             f"${pnl:.2f} | profitable pocket |")

    if not regime_pockets:
        lines.append("| — | — | — | — | — | No profitable pockets found |")
    lines.append("")

    # Strategy pockets: which strategy was profitable on losing tickers?
    lines.append("### Profitable Strategy Pockets (on losing tickers)")
    lines.append("")
    lines.append("| Ticker | Strategy | Trades | WR% | Net PnL | Expectancy |")
    lines.append("|--------|----------|--------|-----|---------|------------|")

    strat_pockets = []
    for ticker in losing_tickers:
        t = trades[trades["Ticker"] == ticker]
        for strat in sorted(t["Strategy"].unique()):
            s = t[t["Strategy"] == strat]
            if len(s) < 3:
                continue
            pnl = s["PnL"].sum()
            wr = 100 * s["Winner"].mean()
            sw = s[s["Winner"]]
            sl = s[~s["Winner"]]
            avg_w = sw["PnL"].mean() if len(sw) else 0
            avg_l = sl["PnL"].mean() if len(sl) else 0
            exp = wr / 100 * avg_w + (1 - wr / 100) * avg_l
            if pnl > 0:
                strat_pockets.append((ticker, strat, len(s), wr, pnl, exp))
                lines.append(f"| {ticker} | {strat} | {len(s)} | {wr:.1f} | "
                             f"${pnl:.2f} | ${exp:.2f} |")

    if not strat_pockets:
        lines.append("| — | — | — | — | — | — |")
    lines.append("")

    # Summary
    lines.append(f"**Summary:** {len(regime_pockets)} profitable regime pockets "
                 f"and {len(strat_pockets)} profitable strategy pockets found "
                 f"across {len(losing_tickers)} losing tickers.")
    lines.append("")

    return lines


# ═══════════════════════════════════════════════════════════════════════════
# Analysis 3: Cross-ticker patterns
# ═══════════════════════════════════════════════════════════════════════════

def analyze_cross_ticker(trades: pd.DataFrame,
                         ticker_meta: dict) -> list[str]:
    """Find universal patterns across all tickers."""
    lines = []
    lines.append("## 3. Cross-Ticker Patterns")
    lines.append("")

    # ── 3a. Composite score threshold sweep ──
    lines.append("### 3a. Composite Score Threshold Sweep")
    lines.append("")
    lines.append("| Threshold | Trades | Win Rate% | Avg PnL | Total PnL | PF |")
    lines.append("|-----------|--------|-----------|---------|-----------|-----|")

    for thresh in range(40, 95, 5):
        subset = trades[trades["Score"] >= thresh]
        if len(subset) < 5:
            lines.append(f"| >= {thresh} | {len(subset)} | — | — | — | — |")
            continue
        wr = 100 * subset["Winner"].mean()
        avg_pnl = subset["PnL"].mean()
        total_pnl = subset["PnL"].sum()
        wins_pnl = subset[subset["Winner"]]["PnL"].sum()
        loss_pnl = abs(subset[~subset["Winner"]]["PnL"].sum())
        pf = wins_pnl / loss_pnl if loss_pnl > 0 else float("inf")
        lines.append(f"| >= {thresh} | {len(subset)} | {wr:.1f} | "
                     f"${avg_pnl:.2f} | ${total_pnl:.2f} | {pf:.2f} |")
    lines.append("")

    # Find the crossover point
    for thresh in range(40, 95, 5):
        subset = trades[trades["Score"] >= thresh]
        if len(subset) >= 5 and subset["Winner"].mean() >= 0.5:
            lines.append(f"**Key finding:** Win rate crosses 50% at composite score "
                         f">= {thresh} ({len(subset)} trades, "
                         f"{100*subset['Winner'].mean():.1f}% WR)")
            break
    else:
        lines.append("**Key finding:** Win rate never reaches 50% at any threshold "
                     "(strategy generates edge through W/L ratio, not win rate)")
    lines.append("")

    # ── 3b. Indicator predictive value at entry ──
    lines.append("### 3b. Indicator Conditions at Entry (Predictive Value)")
    lines.append("")
    lines.append("For each binary indicator condition, what is the win rate when True vs False?")
    lines.append("")
    lines.append("| Condition | Trades (True) | WR% True | Trades (False) | WR% False | Delta |")
    lines.append("|-----------|---------------|----------|----------------|-----------|-------|")

    # Collect indicator values at entry dates per trade
    conditions = _build_indicator_conditions(trades, ticker_meta)
    for cond_name, (true_wr, true_n, false_wr, false_n) in sorted(
            conditions.items(), key=lambda x: abs(x[1][0] - x[1][2]), reverse=True):
        delta = true_wr - false_wr
        lines.append(f"| {cond_name} | {true_n} | {true_wr:.1f} | "
                     f"{false_n} | {false_wr:.1f} | {delta:+.1f} |")
    lines.append("")

    # ── 3c. Signal frequency vs profitability ──
    lines.append("### 3c. Signal Frequency vs Profitability")
    lines.append("")
    lines.append("| Ticker | Trades | Months | Signals/Month | Net PnL | Profitable? |")
    lines.append("|--------|--------|--------|---------------|---------|-------------|")

    freq_data = []
    for ticker in sorted(trades["Ticker"].unique()):
        t = trades[trades["Ticker"] == ticker]
        if len(t) < 5:
            continue
        months = (t["Exit Date"].max() - t["Entry Date"].min()).days / 30.44
        if months <= 0:
            continue
        freq = len(t) / months
        pnl = t["PnL"].sum()
        profitable = "Yes" if pnl > 0 else "No"
        freq_data.append((ticker, len(t), months, freq, pnl, profitable))
        lines.append(f"| {ticker} | {len(t)} | {months:.0f} | {freq:.2f} | "
                     f"${pnl:.2f} | {profitable} |")
    lines.append("")

    # Correlation
    if freq_data:
        freqs = [f[3] for f in freq_data]
        pnls = [f[4] for f in freq_data]
        if len(freqs) > 2:
            corr = np.corrcoef(freqs, pnls)[0, 1]
            lines.append(f"**Frequency-PnL correlation:** {corr:.3f} "
                         f"({'positive — more signals, more profit' if corr > 0.2 else 'negative — fewer signals, better results' if corr < -0.2 else 'weak — frequency not predictive'})")
            lines.append("")

            # Optimal frequency
            profitable_freq = [f[3] for f in freq_data if f[4] > 0]
            unprofitable_freq = [f[3] for f in freq_data if f[4] <= 0]
            if profitable_freq and unprofitable_freq:
                lines.append(f"**Avg frequency:** Profitable tickers = "
                             f"{np.mean(profitable_freq):.2f} signals/mo, "
                             f"Unprofitable = {np.mean(unprofitable_freq):.2f} signals/mo")
    lines.append("")

    return lines


def _build_indicator_conditions(trades: pd.DataFrame,
                                ticker_meta: dict) -> dict:
    """Check indicator conditions at trade entry and compute win rates."""
    conditions = defaultdict(lambda: [0, 0, 0, 0])  # true_wins, true_total, false_wins, false_total

    for _, row in trades.iterrows():
        ticker = row["Ticker"]
        if ticker not in ticker_meta:
            continue
        df, meta, _ = ticker_meta[ticker]
        entry_dt = row["Entry Date"]
        if entry_dt not in df.index:
            continue

        ind = meta["indicators"]
        is_win = row["Winner"]
        close = df["Close"].loc[entry_dt]

        checks = {
            "RSI > 50": ind["rsi14"].loc[entry_dt] > 50,
            "RSI 40-60": 40 < ind["rsi14"].loc[entry_dt] < 60,
            "ADX > 30": ind["adx"].loc[entry_dt] > 30,
            "ADX > 25": ind["adx"].loc[entry_dt] > 25,
            "Close > EMA200": close > ind["ema200"].loc[entry_dt],
            "Close > VWAP": close > ind["vwap"].loc[entry_dt],
            "MACD > Signal": ind["macd_line"].loc[entry_dt] > ind["signal_line"].loc[entry_dt],
            "EMA9 > EMA21": ind["ema9"].loc[entry_dt] > ind["ema21"].loc[entry_dt],
            "Chop < 50": ind["chop"].loc[entry_dt] < 50,
            "Vol above avg": bool(ind["vol_above_avg"].loc[entry_dt]),
            "Stoch K > 50": ind["stoch_k"].loc[entry_dt] > 50,
        }

        for name, val in checks.items():
            if pd.isna(val):
                continue
            if val:
                conditions[name][0] += int(is_win)
                conditions[name][1] += 1
            else:
                conditions[name][2] += int(is_win)
                conditions[name][3] += 1

    result = {}
    for name, (tw, tt, fw, ft) in conditions.items():
        true_wr = 100 * tw / tt if tt >= 5 else 0
        false_wr = 100 * fw / ft if ft >= 5 else 0
        if tt >= 5 and ft >= 5:
            result[name] = (true_wr, tt, false_wr, ft)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Report writer
# ═══════════════════════════════════════════════════════════════════════════

def write_report(trades: pd.DataFrame, ticker_meta: dict) -> Path:
    """Generate the full analysis report."""
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "strategy_analysis.md"

    lines = []
    lines.append("# Strategy Analysis — What Actually Works")
    lines.append("")
    lines.append(f"*Generated from {len(trades)} trades across "
                 f"{trades['Ticker'].nunique()} tickers*")
    lines.append("")

    lines.extend(analyze_profitable(trades))
    lines.extend(analyze_losers(trades))
    lines.extend(analyze_cross_ticker(trades, ticker_meta))

    # ── Key takeaways ──
    lines.append("## Key Takeaways")
    lines.append("")

    # Compute aggregate stats for takeaways
    total_pnl = trades["PnL"].sum()
    overall_wr = 100 * trades["Winner"].mean()

    # Best strategy overall (by total PnL)
    strat_pnl = trades.groupby("Strategy")["PnL"].agg(["sum", "count", "mean"])
    strat_pnl_sorted = strat_pnl.sort_values("sum", ascending=False)
    best_strat = strat_pnl_sorted.index[0]
    best_strat_pnl = strat_pnl_sorted.iloc[0]["sum"]

    # Best regime overall
    regime_pnl = trades.groupby("Regime")["PnL"].agg(["sum", "count", "mean"])
    best_regime = regime_pnl["sum"].idxmax()

    # Worst regime
    worst_regime = regime_pnl["sum"].idxmin()

    # High-score trades
    high_score = trades[trades["Score"] >= 70]
    high_wr = 100 * high_score["Winner"].mean() if len(high_score) >= 5 else 0

    # All strategies ranked
    lines.append("**Strategy ranking by P&L:**")
    lines.append("")
    for sname in strat_pnl_sorted.index:
        row = strat_pnl_sorted.loc[sname]
        lines.append(f"- {sname}: ${row['sum']:.2f} net "
                     f"({int(row['count'])} trades, "
                     f"${row['mean']:.2f}/trade)")
    lines.append("")

    lines.append(f"1. **Best strategy:** {best_strat} "
                 f"(${best_strat_pnl:.2f} net across "
                 f"{int(strat_pnl.loc[best_strat, 'count'])} trades)")
    lines.append(f"2. **Best regime:** {best_regime} "
                 f"(${regime_pnl.loc[best_regime, 'sum']:.2f} net) — "
                 f"**Worst regime:** {worst_regime} "
                 f"(${regime_pnl.loc[worst_regime, 'sum']:.2f} net)")
    lines.append(f"3. **Overall win rate:** {overall_wr:.1f}% "
                 f"(edge comes from W/L ratio, not win rate)")
    lines.append(f"4. **High-score trades (>= 70):** {high_wr:.1f}% WR "
                 f"on {len(high_score)} trades "
                 f"(${high_score['PnL'].sum():.2f} net)")

    # Score >= 85 is the breakeven zone
    score_85 = trades[trades["Score"] >= 85]
    if len(score_85) >= 3:
        lines.append(f"5. **Score >= 85:** {100*score_85['Winner'].mean():.1f}% WR "
                     f"on {len(score_85)} trades "
                     f"(${score_85['PnL'].sum():.2f} net) — the only profitable threshold")

    # Winners hold longer?
    avg_hold_w = trades[trades["Winner"]]["Holding Days"].mean()
    avg_hold_l = trades[~trades["Winner"]]["Holding Days"].mean()
    lines.append(f"6. **Holding period:** Winners avg {avg_hold_w:.1f} days "
                 f"vs Losers avg {avg_hold_l:.1f} days "
                 f"({'winners hold longer — let winners run' if avg_hold_w > avg_hold_l else 'losers hold longer'})")

    # Top indicator predictors
    conditions = _build_indicator_conditions(trades, ticker_meta)
    top_indicators = sorted(conditions.items(),
                            key=lambda x: abs(x[1][0] - x[1][2]), reverse=True)[:3]
    lines.append(f"7. **Best entry filters:** "
                 + ", ".join(f"{name} (+{abs(tw-fw):.1f}% WR delta)"
                             for name, (tw, _, fw, _) in top_indicators))
    lines.append("")

    out_path.write_text("\n".join(lines))
    return out_path


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Collecting trades from all tickers...")
    trades, ticker_meta = collect_all_trades()
    print(f"  {len(trades)} trades across {trades['Ticker'].nunique()} tickers\n")

    print("Running analysis...")
    report_path = write_report(trades, ticker_meta)

    print(f"\nReport written to: {report_path}")
    print("\n" + "=" * 65)

    # Print the report to console too
    print(report_path.read_text())
