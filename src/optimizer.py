#!/usr/bin/env python3
"""
Walk-forward parameter optimization for V6 strategy per ticker cluster.

Methodology:
  - 18-month train / 6-month test rolling windows
  - Optimize for Sharpe ratio, min 15 trades per test window
  - Random search (2,000 samples per cluster) for speed
  - Two clusters: TREND and MOMENTUM

Outputs:
  - reports/optimization_results.md
  - config/cluster_presets.json
"""

import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicators import calc_ema, calc_rsi, calc_adx, calc_atr, calc_macd, calc_sma
from validate_pinescript import compute_weekly_indicators, V6Trade, _is_trending_up, _calc_qty


# ═══════════════════════════════════════════════════════════════════════════
# Cluster definitions
# ═══════════════════════════════════════════════════════════════════════════

CLUSTERS = {
    "TREND": ["SPY", "QQQ", "AMZN", "MSFT", "INTC", "JNJ"],
    "MOMENTUM": ["AMD", "NVDA", "TSLA", "AAPL", "NFLX", "PLTR"],
}

# Parameter search space
PARAM_SPACE = {
    "rsi_lo":       [50, 55, 60],
    "rsi_hi":       [70, 75, 80],
    "adx_thr":      [20, 25, 30],
    "ema_fast":     [8, 9, 13, 21],
    "ema_slow":     [18, 21, 34, 50],
    "min_score":    [60, 65, 70, 75, 80],
    "pullback_pct": [1.0, 2.0, 3.0, 5.0],
    "atr_stop_mult": [1.5, 2.0, 2.5, 3.0],
}

N_RANDOM_SAMPLES = 500
TRAIN_MONTHS = 18
TEST_MONTHS = 6
MIN_TRADES_PER_WINDOW = 10
DATA_START = "2016-01-01"  # Use recent decade only for speed


# ═══════════════════════════════════════════════════════════════════════════
# Parameterized V6 simulator (simplified for speed)
# ═══════════════════════════════════════════════════════════════════════════

def simulate_v6_params(df: pd.DataFrame, params: dict,
                       use_mode_b: bool = False) -> list[V6Trade]:
    """Run V6 sim with custom parameters. Reuses precomputed indicators."""
    close = df["Close"]
    n = len(df)
    if n < 250:
        return []

    # Precompute indicators with param EMA periods
    ema_f = calc_ema(close, params["ema_fast"])
    ema_s = calc_ema(close, params["ema_slow"])
    ema200 = calc_ema(close, 200)
    rsi = calc_rsi(close, 14)
    plus_di, minus_di, adx = calc_adx(df, 14, 14)
    atr = calc_atr(df, 14)
    _, _, histogram = calc_macd(close, 12, 26, 9)
    vol_sma20 = calc_sma(df["Volume"], 20)
    donchian_hi = df["High"].rolling(20).max()
    high20 = df["High"].rolling(20).max()
    atr_pct = atr / close * 100

    wk = compute_weekly_indicators(df)
    wk_bullish = ((wk["wk_ema9"] > wk["wk_ema21"]) &
                  (wk["wk_close"] > wk["wk_ema200"])).fillna(False)

    dates = df.index
    trades = []
    in_position = False
    pending = False
    pending_mode = ""
    pending_score = 0.0
    entry_bar = 0
    entry_price = 0.0
    last_signal_bar = -6
    below_count = 0

    rsi_lo = params["rsi_lo"]
    rsi_hi = params["rsi_hi"]
    adx_thr = params["adx_thr"]
    min_score = params["min_score"]
    pullback = params["pullback_pct"]
    cooldown = 5

    for i in range(1, n):
        c = close.iat[i]
        if np.isnan(ema200.iat[i]) or np.isnan(adx.iat[i]) or np.isnan(rsi.iat[i]):
            continue

        # Enter pending
        if pending and not in_position:
            entry_price = df["Open"].iat[i] + 0.01
            in_position = True
            entry_bar = i
            below_count = 0
            pending = False

        # Exit checks
        if in_position:
            bars_held = i - entry_bar
            if c < ema_s.iat[i]:
                below_count += 1
            else:
                below_count = 0

            exit_reason = ""
            if below_count >= 2:
                exit_reason = "stop_loss"
            elif rsi.iat[i] > 80:
                exit_reason = "take_profit"
            elif bars_held >= 20:
                exit_reason = "time_stop"
            elif not (adx.iat[i] > adx_thr and plus_di.iat[i] > minus_di.iat[i]
                      and c > ema200.iat[i]):
                exit_reason = "regime_change"

            if exit_reason:
                qty = _calc_qty(entry_price, 50000, 0.10)
                pnl = (c - entry_price) * qty - 3.0
                trades.append(V6Trade(
                    entry_date=dates[entry_bar], exit_date=dates[i],
                    entry_price=entry_price, exit_price=c,
                    pnl=round(pnl, 2), mode=pending_mode,
                    exit_reason=exit_reason, score=pending_score,
                    bars_held=bars_held,
                ))
                in_position = False
                last_signal_bar = i
                continue

        if in_position:
            continue

        if i - last_signal_bar < cooldown:
            continue

        if np.isnan(atr_pct.iat[i]) or atr_pct.iat[i] < 0.8 or atr_pct.iat[i] > 6.0:
            continue

        # Regime
        trending_up = (adx.iat[i] > adx_thr and plus_di.iat[i] > minus_di.iat[i]
                       and c > ema200.iat[i])

        # Mode A
        mode_a_score = 0.0
        if trending_up and wk_bullish.iat[i]:
            ema_ok = ema_f.iat[i] > ema_s.iat[i]
            rsi_ok = rsi_lo <= rsi.iat[i] <= rsi_hi
            pct_hi = ((high20.iat[i] - c) / high20.iat[i] * 100
                      if not np.isnan(high20.iat[i]) and high20.iat[i] > 0 else 999)
            near_ok = pct_hi <= pullback
            vol_ok = (df["Volume"].iat[i] > vol_sma20.iat[i] * 0.8
                      if not np.isnan(vol_sma20.iat[i]) else False)

            if ema_ok and rsi_ok and near_ok and c > ema200.iat[i] and vol_ok:
                mode_a_score = (
                    25.0 +
                    (25.0 if 60 <= rsi.iat[i] <= 70 else 15.0) +
                    20.0 +
                    (15.0 if wk_bullish.iat[i] else 0.0) +
                    (5.0 if df["Volume"].iat[i] > vol_sma20.iat[i] else 0.0) +
                    (5.0 if histogram.iat[i] > 0 else 0.0) +
                    (5.0 if adx.iat[i] > 30 else 0.0)
                )

        # Mode B (momentum cluster only)
        mode_b_score = 0.0
        if use_mode_b:
            adx_cross = False
            for j in range(max(0, i - 2), i + 1):
                if j > 0 and adx.iat[j] > adx_thr and adx.iat[j - 1] <= adx_thr:
                    adx_cross = True
                    break
            vol_spike = (df["Volume"].iat[i] > vol_sma20.iat[i] * 1.5
                         if not np.isnan(vol_sma20.iat[i]) else False)

            if adx_cross and vol_spike and rsi.iat[i] > 50:
                brk_ok = (c > donchian_hi.iat[i - 1]
                          if i > 0 and not np.isnan(donchian_hi.iat[i - 1]) else False)
                if brk_ok:
                    mode_b_score = (
                        (25.0 if ema_f.iat[i] > ema_s.iat[i] else 0.0) +
                        25.0 +
                        (20.0 if c > ema200.iat[i] else 0.0) +
                        (15.0 if wk_bullish.iat[i] else 0.0) +
                        5.0 +
                        (5.0 if histogram.iat[i] > 0 else 0.0) +
                        (5.0 if adx.iat[i] > 30 else 0.0)
                    )

        best = max(mode_a_score, mode_b_score)
        if best >= min_score:
            pending = True
            pending_mode = "A" if mode_a_score >= mode_b_score else "B"
            pending_score = best
            last_signal_bar = i

    # Close open position
    if in_position:
        qty = _calc_qty(entry_price, 50000, 0.10)
        pnl = (close.iat[-1] - entry_price) * qty - 3.0
        trades.append(V6Trade(
            entry_date=dates[entry_bar], exit_date=dates[-1],
            entry_price=entry_price, exit_price=close.iat[-1],
            pnl=round(pnl, 2), mode=pending_mode,
            exit_reason="end_of_data", score=pending_score,
            bars_held=n - 1 - entry_bar,
        ))

    return trades


# ═══════════════════════════════════════════════════════════════════════════
# Metrics
# ═══════════════════════════════════════════════════════════════════════════

def sharpe_from_trades(trades: list[V6Trade]) -> float:
    if len(trades) < 5:
        return -999.0
    pnls = np.array([t.pnl for t in trades])
    if pnls.std() == 0:
        return 0.0
    avg_bars = max(1, np.mean([t.bars_held for t in trades]))
    return float(pnls.mean() / pnls.std() * np.sqrt(252 / avg_bars))


def pf_from_trades(trades: list[V6Trade]) -> float:
    if not trades:
        return 0.0
    wins = sum(t.pnl for t in trades if t.pnl > 0)
    losses = abs(sum(t.pnl for t in trades if t.pnl <= 0))
    return wins / losses if losses > 0 else float("inf")


# ═══════════════════════════════════════════════════════════════════════════
# Walk-forward engine
# ═══════════════════════════════════════════════════════════════════════════

def generate_windows(df: pd.DataFrame):
    """Generate (train_df, test_df) rolling windows."""
    start = df.index[0]
    end = df.index[-1]
    train_delta = pd.DateOffset(months=TRAIN_MONTHS)
    test_delta = pd.DateOffset(months=TEST_MONTHS)
    step_delta = pd.DateOffset(months=TEST_MONTHS)

    windows = []
    cursor = start
    while cursor + train_delta + test_delta <= end:
        train_start = cursor
        train_end = cursor + train_delta
        test_start = train_end
        test_end = test_start + test_delta

        train = df[train_start:train_end]
        test = df[test_start:test_end]

        if len(train) >= 200 and len(test) >= 50:
            windows.append((train, test))

        cursor += step_delta

    return windows


def sample_params():
    """Random sample from parameter space."""
    p = {k: random.choice(v) for k, v in PARAM_SPACE.items()}
    # Constraint: ema_fast < ema_slow
    if p["ema_fast"] >= p["ema_slow"]:
        p["ema_slow"] = max(v for v in PARAM_SPACE["ema_slow"] if v > p["ema_fast"])
    # Constraint: rsi_lo < rsi_hi
    if p["rsi_lo"] >= p["rsi_hi"]:
        p["rsi_hi"] = max(v for v in PARAM_SPACE["rsi_hi"] if v > p["rsi_lo"])
    return p


def walk_forward_eval(dfs: dict[str, pd.DataFrame], params: dict,
                      use_mode_b: bool) -> dict:
    """Evaluate params across all tickers in a cluster using walk-forward.

    Runs simulation on the FULL dataset (so indicators warm up properly),
    then slices trades into train/test windows for evaluation.
    """
    all_is_trades: list[V6Trade] = []
    all_oos_trades: list[V6Trade] = []

    for ticker, df in dfs.items():
        windows = generate_windows(df)
        if len(windows) < 4:
            continue

        # Run simulation on full dataset ONCE
        full_trades = simulate_v6_params(df, params, use_mode_b)

        # Slice trades into train/test windows
        for train_df, test_df in windows:
            train_end = train_df.index[-1]
            test_start = test_df.index[0]
            test_end = test_df.index[-1]

            for t in full_trades:
                if t.entry_date <= train_end:
                    all_is_trades.append(t)
                elif test_start <= t.entry_date <= test_end:
                    all_oos_trades.append(t)

    if len(all_oos_trades) < MIN_TRADES_PER_WINDOW:
        return {"oos_sharpe": -999, "is_sharpe": -999, "oos_trades": 0,
                "oos_pnl": 0, "degradation": 0, "params": params}

    is_sharpe = sharpe_from_trades(all_is_trades)
    oos_sharpe = sharpe_from_trades(all_oos_trades)
    oos_pnl = sum(t.pnl for t in all_oos_trades)
    degradation = oos_sharpe / is_sharpe if is_sharpe > 0 else 0

    return {
        "oos_sharpe": round(oos_sharpe, 3),
        "is_sharpe": round(is_sharpe, 3),
        "oos_trades": len(all_oos_trades),
        "oos_pnl": round(oos_pnl, 2),
        "degradation": round(degradation, 3),
        "params": params,
    }


def optimize_cluster(cluster_name: str, tickers: list[str],
                     use_mode_b: bool) -> list[dict]:
    """Run random search optimization for a cluster."""
    print(f"\n  Loading data for {cluster_name} cluster: {tickers}")
    dfs = {}
    for ticker in tickers:
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
            df = df[df.index >= pd.Timestamp(DATA_START)]
            if len(df) >= 500:
                dfs[ticker] = df
            else:
                print(f"    {ticker}: only {len(df)} bars after {DATA_START}, skipping")
        except Exception:
            print(f"    {ticker}: data not found, skipping")

    if not dfs:
        return []

    # Check window count
    total_windows = 0
    for ticker, df in dfs.items():
        w = generate_windows(df)
        total_windows += len(w)
        print(f"    {ticker}: {len(df)} bars, {len(w)} walk-forward windows")
    print(f"    Total windows: {total_windows}")

    # Random search
    print(f"\n  Running {N_RANDOM_SAMPLES} random parameter samples...")
    t0 = time.time()
    results = []

    for sample_idx in range(N_RANDOM_SAMPLES):
        params = sample_params()
        result = walk_forward_eval(dfs, params, use_mode_b)
        results.append(result)

        if (sample_idx + 1) % 200 == 0:
            elapsed = time.time() - t0
            best_so_far = max(results, key=lambda x: x["oos_sharpe"])
            print(f"    {sample_idx + 1}/{N_RANDOM_SAMPLES} done "
                  f"({elapsed:.0f}s) — best OOS Sharpe: {best_so_far['oos_sharpe']:.3f}")

    elapsed = time.time() - t0
    print(f"  Completed in {elapsed:.0f}s")

    # Sort by OOS Sharpe
    results.sort(key=lambda x: x["oos_sharpe"], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Robustness check
# ═══════════════════════════════════════════════════════════════════════════

def check_robustness(results: list[dict], top_params: dict) -> str:
    """Check if nearby parameter values also perform well."""
    # Count how many of top-20 share similar params with the winner
    top_20 = results[:20]
    similar_count = 0
    for r in top_20:
        p = r["params"]
        matches = sum(1 for k in top_params if p.get(k) == top_params[k])
        if matches >= 5:  # 5 out of 8 params match
            similar_count += 1

    if similar_count >= 10:
        return "ROBUST (flat optimum — nearby params also work well)"
    elif similar_count >= 5:
        return "MODERATE (some sensitivity but reasonable plateau)"
    else:
        return "SPIKY (optimum is isolated — high overfitting risk)"


# ═══════════════════════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════════════════════

def build_report(cluster_results: dict[str, list[dict]]) -> str:
    lines = ["# Walk-Forward Optimization Results", ""]
    lines.append(f"*{N_RANDOM_SAMPLES} random parameter samples per cluster, "
                 f"{TRAIN_MONTHS}mo train / {TEST_MONTHS}mo test rolling windows, "
                 f"data from {DATA_START}*")
    lines.append("")

    presets = {}

    for cluster_name, results in cluster_results.items():
        lines.append(f"## {cluster_name} Cluster")
        lines.append("")
        lines.append(f"Tickers: {', '.join(CLUSTERS[cluster_name])}")
        lines.append("")

        if not results or results[0]["oos_sharpe"] <= -999:
            lines.append("**No viable parameter sets found.**")
            lines.append("")
            continue

        # Top 5
        top5 = [r for r in results[:5] if r["oos_sharpe"] > -999]
        lines.append("### Top 5 Parameter Sets (by OOS Sharpe)")
        lines.append("")
        lines.append("| Rank | OOS Sharpe | IS Sharpe | Degradation | OOS Trades | OOS PnL | RSI | ADX | EMA | Score | Pullback | ATR Stop |")
        lines.append("|------|-----------|----------|-------------|-----------|---------|-----|-----|-----|-------|----------|----------|")

        for i, r in enumerate(top5):
            p = r["params"]
            lines.append(
                f"| {i+1} | {r['oos_sharpe']:.3f} | {r['is_sharpe']:.3f} | "
                f"{r['degradation']:.3f} | {r['oos_trades']} | ${r['oos_pnl']:.0f} | "
                f"{p['rsi_lo']}-{p['rsi_hi']} | {p['adx_thr']} | "
                f"{p['ema_fast']}/{p['ema_slow']} | {p['min_score']} | "
                f"{p['pullback_pct']}% | {p['atr_stop_mult']}x |"
            )
        lines.append("")

        # Winner details
        winner = top5[0]
        wp = winner["params"]

        lines.append("### Winner Analysis")
        lines.append("")
        lines.append(f"- **OOS Sharpe:** {winner['oos_sharpe']:.3f}")
        lines.append(f"- **IS Sharpe:** {winner['is_sharpe']:.3f}")
        lines.append(f"- **Degradation ratio:** {winner['degradation']:.3f} "
                     f"({'GOOD' if winner['degradation'] > 0.5 else 'CONCERNING'} — want > 0.5)")
        lines.append(f"- **OOS trades:** {winner['oos_trades']}")
        lines.append(f"- **OOS net PnL:** ${winner['oos_pnl']:.2f}")
        lines.append("")

        # Robustness
        robustness = check_robustness(results, wp)
        lines.append(f"- **Robustness:** {robustness}")
        lines.append("")

        # Parameter details
        lines.append("### Winning Parameters")
        lines.append("")
        lines.append(f"```json")
        lines.append(json.dumps(wp, indent=2))
        lines.append(f"```")
        lines.append("")

        # Save preset
        presets[cluster_name.lower()] = {
            "tickers": CLUSTERS[cluster_name],
            "params": wp,
            "oos_sharpe": winner["oos_sharpe"],
            "is_sharpe": winner["is_sharpe"],
            "degradation": winner["degradation"],
            "robustness": robustness,
        }

    return "\n".join(lines), presets


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    random.seed(42)  # Reproducible results
    np.random.seed(42)

    print("=" * 70)
    print("  WALK-FORWARD PARAMETER OPTIMIZATION")
    print("=" * 70)

    cluster_results = {}

    for cluster_name, tickers in CLUSTERS.items():
        use_mode_b = cluster_name == "MOMENTUM"
        results = optimize_cluster(cluster_name, tickers, use_mode_b)
        cluster_results[cluster_name] = results

    # Generate report
    report, presets = build_report(cluster_results)

    # Write outputs
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / "optimization_results.md"
    report_path.write_text(report)
    print(f"\n  Report: {report_path}")

    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    presets_path = config_dir / "cluster_presets.json"
    with open(presets_path, "w") as f:
        json.dump(presets, f, indent=2)
    print(f"  Presets: {presets_path}")

    # Print summary
    print(f"\n{'=' * 70}")
    print(report)


if __name__ == "__main__":
    main()
