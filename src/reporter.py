"""
Performance reporting for Portfolio Scanner V5 backtester.

Calculates detailed metrics, breakdowns by strategy/regime, monthly returns,
generates charts, and produces actionable recommendations.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulator import TradeLog


# ═══════════════════════════════════════════════════════════════════════════
# 1. Core metrics
# ═══════════════════════════════════════════════════════════════════════════

def calculate_metrics(trade_log: TradeLog) -> dict:
    """Calculate comprehensive performance metrics from a TradeLog."""
    df = trade_log.to_dataframe()
    eq = trade_log.equity_curve

    if len(df) == 0:
        return {"total_trades": 0}

    wins = df[df["PnL"] > 0]
    losses = df[df["PnL"] <= 0]
    gross_profit = wins["PnL"].sum() if len(wins) else 0.0
    gross_loss = abs(losses["PnL"].sum()) if len(losses) else 0.0
    net_pnl = df["PnL"].sum()

    # Bars in trade
    bars_col = (df["Exit Date"] - df["Entry Date"]).dt.days
    avg_bars_win = bars_col[df["PnL"] > 0].mean() if len(wins) else 0.0
    avg_bars_loss = bars_col[df["PnL"] <= 0].mean() if len(losses) else 0.0

    # Consecutive wins/losses
    is_win = (df["PnL"] > 0).astype(int)
    max_consec_wins = _max_consecutive(is_win, 1)
    max_consec_losses = _max_consecutive(is_win, 0)

    # Drawdown
    max_dd_dollar = 0.0
    max_dd_pct = 0.0
    if not eq.empty:
        cummax = eq.cummax()
        dd = eq - cummax
        max_dd_dollar = float(dd.min())
        peak_at_dd = cummax[dd.idxmin()] if dd.min() < 0 else eq.iloc[0]
        max_dd_pct = (max_dd_dollar / peak_at_dd * 100) if peak_at_dd != 0 else 0.0

    # Recovery factor
    recovery_factor = abs(net_pnl / max_dd_dollar) if max_dd_dollar < 0 else float("inf")

    # Sharpe / Sortino (annualized, assuming ~252 trading days)
    daily_returns = _daily_returns(trade_log)
    sharpe = _sharpe_ratio(daily_returns)
    sortino = _sortino_ratio(daily_returns)

    # Expectancy
    avg_win = wins["PnL"].mean() if len(wins) else 0.0
    avg_loss = losses["PnL"].mean() if len(losses) else 0.0
    win_rate = len(wins) / len(df) if len(df) else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    return {
        "total_trades": len(df),
        "winners": len(wins),
        "losers": len(losses),
        "win_rate": round(100 * win_rate, 1),
        "net_pnl": round(net_pnl, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_win_loss_ratio": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else float("inf"),
        "max_drawdown_dollar": round(max_dd_dollar, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "recovery_factor": round(recovery_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "expectancy": round(expectancy, 2),
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "avg_bars_winners": round(avg_bars_win, 1),
        "avg_bars_losers": round(avg_bars_loss, 1),
    }


def _max_consecutive(series: pd.Series, value: int) -> int:
    """Count max consecutive occurrences of `value` in series."""
    if series.empty:
        return 0
    groups = (series != value).cumsum()
    runs = series.groupby(groups).sum()
    return int(runs.max()) if len(runs) else 0


def _daily_returns(trade_log: TradeLog) -> pd.Series:
    """Convert equity curve to daily returns."""
    eq = trade_log.equity_curve
    if eq.empty or len(eq) < 2:
        return pd.Series(dtype=float)
    return eq.diff().dropna()


def _sharpe_ratio(daily_returns: pd.Series, risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio."""
    if daily_returns.empty or daily_returns.std() == 0:
        return 0.0
    excess = daily_returns - risk_free / 252
    return float(excess.mean() / excess.std() * np.sqrt(252))


def _sortino_ratio(daily_returns: pd.Series, risk_free: float = 0.0) -> float:
    """Annualized Sortino ratio."""
    if daily_returns.empty:
        return 0.0
    excess = daily_returns - risk_free / 252
    downside = excess[excess < 0]
    if downside.empty or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float(excess.mean() / downside.std() * np.sqrt(252))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Per-strategy breakdown
# ═══════════════════════════════════════════════════════════════════════════

def per_strategy_breakdown(trade_log: TradeLog) -> pd.DataFrame:
    """Calculate metrics per strategy."""
    df = trade_log.to_dataframe()
    if df.empty:
        return pd.DataFrame()

    rows = []
    for strat in sorted(df["Strategy"].unique()):
        subset = df[df["Strategy"] == strat]
        wins = subset[subset["PnL"] > 0]
        losses = subset[subset["PnL"] <= 0]
        gp = wins["PnL"].sum() if len(wins) else 0.0
        gl = abs(losses["PnL"].sum()) if len(losses) else 0.0
        wr = len(wins) / len(subset) if len(subset) else 0.0
        avg_w = wins["PnL"].mean() if len(wins) else 0.0
        avg_l = losses["PnL"].mean() if len(losses) else 0.0
        rows.append({
            "Strategy": strat,
            "Trades": len(subset),
            "Win Rate%": round(100 * wr, 1),
            "Net PnL": round(subset["PnL"].sum(), 2),
            "Profit Factor": round(gp / gl, 2) if gl > 0 else float("inf"),
            "Avg Win": round(avg_w, 2),
            "Avg Loss": round(avg_l, 2),
            "Expectancy": round(wr * avg_w + (1 - wr) * avg_l, 2),
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Per-regime breakdown
# ═══════════════════════════════════════════════════════════════════════════

def per_regime_breakdown(trade_log: TradeLog) -> pd.DataFrame:
    """Calculate metrics per entry regime."""
    df = trade_log.to_dataframe()
    if df.empty:
        return pd.DataFrame()

    rows = []
    for regime in sorted(df["Regime"].unique()):
        subset = df[df["Regime"] == regime]
        wins = subset[subset["PnL"] > 0]
        losses = subset[subset["PnL"] <= 0]
        gp = wins["PnL"].sum() if len(wins) else 0.0
        gl = abs(losses["PnL"].sum()) if len(losses) else 0.0
        wr = len(wins) / len(subset) if len(subset) else 0.0
        rows.append({
            "Regime": regime,
            "Trades": len(subset),
            "Win Rate%": round(100 * wr, 1),
            "Net PnL": round(subset["PnL"].sum(), 2),
            "Profit Factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Monthly returns grid
# ═══════════════════════════════════════════════════════════════════════════

def monthly_returns(trade_log: TradeLog) -> pd.DataFrame:
    """Monthly P&L grid: rows=years, cols=months."""
    df = trade_log.to_dataframe()
    if df.empty:
        return pd.DataFrame()

    df["Year"] = pd.to_datetime(df["Exit Date"]).dt.year
    df["Month"] = pd.to_datetime(df["Exit Date"]).dt.month

    pivot = df.pivot_table(values="PnL", index="Year", columns="Month",
                           aggfunc="sum", fill_value=0.0)
    pivot.columns = [f"{m:02d}" for m in pivot.columns]

    # Add yearly total
    pivot["Total"] = pivot.sum(axis=1)
    return pivot.round(2)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Report generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(trade_log: TradeLog, ticker: str,
                    output_dir: str | Path = "reports") -> Path:
    """Generate all report artifacts for a single ticker."""
    out = Path(output_dir) / ticker
    out.mkdir(parents=True, exist_ok=True)

    metrics = calculate_metrics(trade_log)
    strat_df = per_strategy_breakdown(trade_log)
    regime_df = per_regime_breakdown(trade_log)
    monthly = monthly_returns(trade_log)

    # ── Text summary ──
    _write_text_report(out / "performance_summary.txt", ticker, metrics,
                       strat_df, regime_df, monthly)

    # ── Trade log CSV ──
    trade_df = trade_log.to_dataframe()
    if not trade_df.empty:
        trade_df.to_csv(out / "trade_log.csv", index=False)

    # ── Charts ──
    if not trade_log.equity_curve.empty and len(trade_log.trades) > 0:
        _plot_equity_curve(trade_log, ticker, out)
        _plot_drawdown(trade_log, ticker, out)
    if not monthly.empty:
        _plot_monthly_heatmap(monthly, ticker, out)
    if not strat_df.empty:
        _plot_strategy_comparison(strat_df, ticker, out)

    return out


def _write_text_report(path: Path, ticker: str, metrics: dict,
                       strat_df: pd.DataFrame, regime_df: pd.DataFrame,
                       monthly: pd.DataFrame) -> None:
    lines = []
    lines.append("=" * 70)
    lines.append(f"  PERFORMANCE REPORT — {ticker}")
    lines.append("=" * 70)

    if metrics.get("total_trades", 0) == 0:
        lines.append("  No trades executed.")
        path.write_text("\n".join(lines))
        return

    lines.append("")
    lines.append("  CORE METRICS")
    lines.append("  " + "-" * 40)
    for key in ["total_trades", "winners", "losers", "win_rate",
                "net_pnl", "gross_profit", "gross_loss", "profit_factor",
                "avg_win", "avg_loss", "avg_win_loss_ratio",
                "max_drawdown_dollar", "max_drawdown_pct", "recovery_factor",
                "sharpe_ratio", "sortino_ratio", "expectancy",
                "max_consecutive_wins", "max_consecutive_losses",
                "avg_bars_winners", "avg_bars_losers"]:
        label = key.replace("_", " ").title()
        val = metrics.get(key, "n/a")
        if isinstance(val, float):
            if "pct" in key or "rate" in key:
                lines.append(f"  {label:<30s}  {val:>10.1f}%")
            elif "ratio" in key or "factor" in key:
                lines.append(f"  {label:<30s}  {val:>10.2f}")
            else:
                lines.append(f"  {label:<30s}  ${val:>10.2f}")
        else:
            lines.append(f"  {label:<30s}  {val:>10}")

    lines.append("")
    lines.append("  PER-STRATEGY BREAKDOWN")
    lines.append("  " + "-" * 40)
    if not strat_df.empty:
        lines.append(tabulate(strat_df, headers="keys", tablefmt="simple",
                              showindex=False, floatfmt=".2f"))

    lines.append("")
    lines.append("  PER-REGIME BREAKDOWN")
    lines.append("  " + "-" * 40)
    if not regime_df.empty:
        lines.append(tabulate(regime_df, headers="keys", tablefmt="simple",
                              showindex=False, floatfmt=".2f"))

    lines.append("")
    lines.append("  MONTHLY RETURNS")
    lines.append("  " + "-" * 40)
    if not monthly.empty:
        lines.append(tabulate(monthly, headers="keys", tablefmt="simple",
                              floatfmt=".2f"))

    path.write_text("\n".join(lines))


def _plot_equity_curve(trade_log: TradeLog, ticker: str, out: Path) -> None:
    eq = trade_log.equity_curve
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(eq.index, eq.values, color="steelblue", linewidth=1.2)
    ax.axhline(y=eq.iloc[0], color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.fill_between(eq.index, eq.iloc[0], eq.values,
                    where=eq.values >= eq.iloc[0], alpha=0.15, color="green")
    ax.fill_between(eq.index, eq.iloc[0], eq.values,
                    where=eq.values < eq.iloc[0], alpha=0.15, color="red")
    ax.set_title(f"{ticker} — Equity Curve", fontsize=13)
    ax.set_ylabel("Equity ($)")
    fig.tight_layout()
    fig.savefig(out / "equity_curve.png", dpi=150)
    plt.close(fig)


def _plot_drawdown(trade_log: TradeLog, ticker: str, out: Path) -> None:
    eq = trade_log.equity_curve
    cummax = eq.cummax()
    dd = eq - cummax

    fig, ax = plt.subplots(figsize=(14, 4))
    ax.fill_between(dd.index, 0, dd.values, color="red", alpha=0.4)
    ax.plot(dd.index, dd.values, color="darkred", linewidth=0.8)
    ax.set_title(f"{ticker} — Drawdown", fontsize=13)
    ax.set_ylabel("Drawdown ($)")
    fig.tight_layout()
    fig.savefig(out / "drawdown_chart.png", dpi=150)
    plt.close(fig)


def _plot_monthly_heatmap(monthly: pd.DataFrame, ticker: str, out: Path) -> None:
    # Drop the Total column for heatmap
    data = monthly.drop(columns=["Total"], errors="ignore")
    if data.empty:
        return

    fig, ax = plt.subplots(figsize=(12, max(3, len(data) * 0.4)))

    # Color normalization: green positive, red negative
    vmax = max(abs(data.values.max()), abs(data.values.min()), 1)
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    cmap = plt.cm.RdYlGn

    im = ax.imshow(data.values, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(data.columns)))
    ax.set_xticklabels(data.columns, fontsize=9)
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels(data.index, fontsize=9)

    # Annotate cells
    for y in range(data.shape[0]):
        for x in range(data.shape[1]):
            val = data.values[y, x]
            if val != 0:
                ax.text(x, y, f"{val:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(val) > vmax * 0.6 else "black")

    ax.set_title(f"{ticker} — Monthly P&L", fontsize=13)
    fig.colorbar(im, ax=ax, shrink=0.8, label="P&L ($)")
    fig.tight_layout()
    fig.savefig(out / "monthly_heatmap.png", dpi=150)
    plt.close(fig)


def _plot_strategy_comparison(strat_df: pd.DataFrame, ticker: str, out: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    strats = strat_df["Strategy"].tolist()
    x = range(len(strats))
    short_names = [s.replace("S1_TrendFollowing", "S1-Trend")
                    .replace("S2_MeanReversion", "S2-MeanRev")
                    .replace("S3_BreakoutMomentum", "S3-Breakout")
                    .replace("S4_RangeScalp", "S4-Scalp")
                   for s in strats]

    # Net PnL
    colors = ["green" if v > 0 else "red" for v in strat_df["Net PnL"]]
    axes[0].bar(x, strat_df["Net PnL"], color=colors, alpha=0.7)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(short_names, fontsize=8, rotation=15)
    axes[0].set_title("Net P&L ($)")
    axes[0].axhline(0, color="gray", linewidth=0.5)

    # Win Rate
    axes[1].bar(x, strat_df["Win Rate%"], color="steelblue", alpha=0.7)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(short_names, fontsize=8, rotation=15)
    axes[1].set_title("Win Rate (%)")
    axes[1].axhline(50, color="gray", linewidth=0.5, linestyle="--")

    # Expectancy
    colors_e = ["green" if v > 0 else "red" for v in strat_df["Expectancy"]]
    axes[2].bar(x, strat_df["Expectancy"], color=colors_e, alpha=0.7)
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(short_names, fontsize=8, rotation=15)
    axes[2].set_title("Expectancy ($/trade)")
    axes[2].axhline(0, color="gray", linewidth=0.5)

    fig.suptitle(f"{ticker} — Strategy Comparison", fontsize=13)
    fig.tight_layout()
    fig.savefig(out / "strategy_comparison.png", dpi=150)
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Recommendations
# ═══════════════════════════════════════════════════════════════════════════

def recommend_changes(metrics: dict, per_strategy: pd.DataFrame,
                      per_regime: pd.DataFrame) -> list[str]:
    """Generate actionable suggestions based on backtest results."""
    recs = []

    if metrics.get("total_trades", 0) == 0:
        recs.append("No trades were generated. Consider lowering the composite "
                     "score threshold or relaxing regime filters.")
        return recs

    # Overall health
    wr = metrics.get("win_rate", 0)
    pf = metrics.get("profit_factor", 0)
    expectancy = metrics.get("expectancy", 0)

    if expectancy < 0:
        recs.append(f"NEGATIVE expectancy (${expectancy:.2f}/trade). "
                    "Review stop/target distances and entry quality.")

    if wr < 30:
        recs.append(f"Win rate is very low ({wr:.0f}%). Consider tightening "
                    "entry filters or increasing the composite score threshold.")
    elif wr > 65:
        recs.append(f"Win rate is high ({wr:.0f}%). Consider widening targets "
                    "to capture larger moves — the edge may support it.")

    if pf < 1.0 and pf > 0:
        recs.append(f"Profit factor below 1.0 ({pf:.2f}). The system is net "
                    "negative. Prioritize reducing losing trade size.")

    dd_pct = abs(metrics.get("max_drawdown_pct", 0))
    if dd_pct > 20:
        recs.append(f"Max drawdown is {dd_pct:.1f}% — consider reducing "
                    "position size or tightening daily loss limits.")

    # Per-strategy recommendations
    if not per_strategy.empty:
        for _, row in per_strategy.iterrows():
            sname = row["Strategy"]
            s_pf = row.get("Profit Factor", 0)
            s_trades = row.get("Trades", 0)
            s_exp = row.get("Expectancy", 0)

            if s_trades < 5:
                recs.append(f"{sname}: Only {s_trades} trades — insufficient "
                            "sample size. May need longer backtest or relaxed filters.")
            elif s_exp < 0:
                recs.append(f"{sname}: Negative expectancy (${s_exp:.2f}). "
                            "Consider disabling or re-tuning parameters.")
            elif s_pf > 2.0 and s_trades >= 10:
                recs.append(f"{sname}: Strong performance (PF={s_pf:.1f}). "
                            "Consider increasing allocation to this strategy.")

    # Per-regime recommendations
    if not per_regime.empty:
        for _, row in per_regime.iterrows():
            regime = row["Regime"]
            r_pnl = row.get("Net PnL", 0)
            r_trades = row.get("Trades", 0)
            if r_trades >= 5 and r_pnl < 0:
                recs.append(f"Regime '{regime}': Net loss (${r_pnl:.2f} over "
                            f"{r_trades} trades). Consider adjusting ADX/Chop "
                            "thresholds for this regime.")

    if not recs:
        recs.append("Performance looks solid. No immediate changes recommended.")

    return recs


# ═══════════════════════════════════════════════════════════════════════════
# Print summary helper (for console output)
# ═══════════════════════════════════════════════════════════════════════════

def print_report_summary(ticker: str, metrics: dict, strat_df: pd.DataFrame,
                         regime_df: pd.DataFrame, recs: list[str]) -> None:
    """Print a concise summary to console."""
    print(f"\n{'=' * 65}")
    print(f"  {ticker} — PERFORMANCE SUMMARY")
    print(f"{'=' * 65}")

    if metrics.get("total_trades", 0) == 0:
        print("  No trades.\n")
        return

    print(f"  Trades: {metrics['total_trades']}  |  "
          f"WR: {metrics['win_rate']}%  |  "
          f"PF: {metrics['profit_factor']}  |  "
          f"Net: ${metrics['net_pnl']}")
    print(f"  Sharpe: {metrics['sharpe_ratio']}  |  "
          f"Sortino: {metrics['sortino_ratio']}  |  "
          f"MaxDD: ${metrics['max_drawdown_dollar']}  "
          f"({metrics['max_drawdown_pct']}%)")
    print(f"  Expectancy: ${metrics['expectancy']}/trade  |  "
          f"Avg W: ${metrics['avg_win']}  |  "
          f"Avg L: ${metrics['avg_loss']}  |  "
          f"W/L: {metrics['avg_win_loss_ratio']}x")
    print(f"  Consec W: {metrics['max_consecutive_wins']}  |  "
          f"Consec L: {metrics['max_consecutive_losses']}  |  "
          f"Avg bars W: {metrics['avg_bars_winners']}  |  "
          f"Avg bars L: {metrics['avg_bars_losers']}")

    if not strat_df.empty:
        print(f"\n  Strategy breakdown:")
        print(tabulate(strat_df, headers="keys", tablefmt="simple",
                       showindex=False, floatfmt=".2f"))

    if not regime_df.empty:
        print(f"\n  Regime breakdown:")
        print(tabulate(regime_df, headers="keys", tablefmt="simple",
                       showindex=False, floatfmt=".2f"))

    print(f"\n  Recommendations:")
    for r in recs:
        print(f"    - {r}")
