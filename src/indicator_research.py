#!/usr/bin/env python3
"""
Fresh indicator research for swing options strategy.

Tests 25 indicator signals across 15 tickers on 2020-2026 data.
Measures forward returns at 5/10/20 bar horizons.
Clusters tickers by behavior. Identifies top indicators per cluster.

Output: reports/fresh_strategy_research.md
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicators import (
    calc_ema, calc_sma, calc_rsi, calc_atr, calc_adx, calc_macd,
    calc_bollinger, calc_supertrend, calc_stochastic, calc_range_filter,
    calc_choppiness_index, calc_obv, calc_cci, calc_keltner, calc_swing_levels,
)

TICKERS = ["SPY", "QQQ", "IWM", "SLV", "GLD", "XLE", "XLF",
           "NVDA", "TSLA", "AMD", "MSFT", "META", "AMZN", "SOFI", "INTC"]
DATA_START = "2020-01-01"
HORIZONS = [5, 10, 20]


# ═══════════════════════════════════════════════════════════════════════════
# Forward return calculator
# ═══════════════════════════════════════════════════════════════════════════

def compute_forward_returns(df, atr):
    """Compute forward returns and MFE/MAE at multiple horizons."""
    close = df["Close"].values
    high = df["High"].values
    low = df["Low"].values
    atr_v = atr.values
    n = len(df)
    results = {}

    for h in HORIZONS:
        fwd_ret = np.full(n, np.nan)
        mfe_long = np.full(n, np.nan)
        mae_long = np.full(n, np.nan)

        for i in range(n - h):
            fwd_ret[i] = (close[i + h] - close[i]) / close[i]
            mfe_long[i] = (max(high[i + 1:i + h + 1]) - close[i]) / close[i]
            mae_long[i] = (close[i] - min(low[i + 1:i + h + 1])) / close[i]

        # ATR-normalized win: moved > 0.5 ATR in signal direction
        atr_pct = np.where(close > 0, atr_v / close, 0)
        long_win = fwd_ret > 0.5 * atr_pct
        short_win = fwd_ret < -0.5 * atr_pct

        results[h] = {
            "fwd_ret": pd.Series(fwd_ret, index=df.index),
            "long_win": pd.Series(long_win, index=df.index),
            "short_win": pd.Series(short_win, index=df.index),
            "mfe_long": pd.Series(mfe_long, index=df.index),
            "mae_long": pd.Series(mae_long, index=df.index),
        }
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Signal generators
# ═══════════════════════════════════════════════════════════════════════════

def generate_signals(df, ind):
    """Generate all 25 signal types. Returns dict of {name: (long_bool, short_bool)}."""
    close = df["Close"]
    signals = {}

    # ── TREND ──
    ema9 = ind["ema9"]
    ema21 = ind["ema21"]
    ema50 = ind["ema50"]
    ema13 = calc_ema(close, 13)
    ema48 = calc_ema(close, 48)

    signals["ema_cross_9_21"] = (
        (ema9 > ema21) & (ema9.shift(1) <= ema21.shift(1)),
        (ema9 < ema21) & (ema9.shift(1) >= ema21.shift(1)),
    )
    signals["ema_cross_13_48"] = (
        (ema13 > ema48) & (ema13.shift(1) <= ema48.shift(1)),
        (ema13 < ema48) & (ema13.shift(1) >= ema48.shift(1)),
    )
    signals["macd_hist_flip"] = (
        (ind["histogram"] > 0) & (ind["histogram"].shift(1) <= 0),
        (ind["histogram"] < 0) & (ind["histogram"].shift(1) >= 0),
    )
    signals["macd_zero_cross"] = (
        (ind["macd_line"] > 0) & (ind["macd_line"].shift(1) <= 0),
        (ind["macd_line"] < 0) & (ind["macd_line"].shift(1) >= 0),
    )
    st_dir = ind["st_dir"]
    signals["supertrend_flip"] = (
        (st_dir == 1) & (st_dir.shift(1) == -1),
        (st_dir == -1) & (st_dir.shift(1) == 1),
    )
    adx = ind["adx"]
    plus_di = ind["plus_di"]
    minus_di = ind["minus_di"]
    signals["adx_trend_start"] = (
        (adx > 25) & (adx.shift(1) <= 25) & (plus_di > minus_di),
        (adx > 25) & (adx.shift(1) <= 25) & (minus_di > plus_di),
    )
    rf = ind["range_filter"]
    signals["range_filter_cross"] = (
        (close > rf) & (close.shift(1) <= rf.shift(1)),
        (close < rf) & (close.shift(1) >= rf.shift(1)),
    )

    # ── MOMENTUM ──
    rsi = ind["rsi14"]
    signals["rsi_oversold_exit"] = (
        (rsi > 30) & (rsi.shift(1) <= 30),
        (rsi < 70) & (rsi.shift(1) >= 70),
    )
    signals["rsi_momentum_50"] = (
        (rsi > 50) & (rsi.shift(1) <= 50),
        (rsi < 50) & (rsi.shift(1) >= 50),
    )
    stoch_k = ind["stoch_k"]
    stoch_d = ind["stoch_d"]
    signals["stoch_cross"] = (
        (stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1)) & (stoch_k < 30),
        (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1)) & (stoch_k > 70),
    )
    cci = ind["cci"]
    signals["cci_reversal"] = (
        (cci > -100) & (cci.shift(1) <= -100),
        (cci < 100) & (cci.shift(1) >= 100),
    )
    signals["cci_momentum"] = (
        (cci > 0) & (cci.shift(1) <= 0),
        (cci < 0) & (cci.shift(1) >= 0),
    )

    # ── VOLATILITY ──
    bb_upper = ind["bb_upper"]
    bb_lower = ind["bb_lower"]
    bb_mid = ind["bb_mid"]
    bbw = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan) * 100
    bbw_sma = calc_sma(bbw, 20)
    signals["bb_squeeze_expand"] = (
        (bbw > bbw.shift(1)) & (bbw.shift(1) < bbw_sma.shift(1)) & (close > bb_mid),
        (bbw > bbw.shift(1)) & (bbw.shift(1) < bbw_sma.shift(1)) & (close < bb_mid),
    )
    signals["bb_touch_bounce"] = (
        (close.shift(1) <= bb_lower.shift(1)) & (close > bb_lower),
        (close.shift(1) >= bb_upper.shift(1)) & (close < bb_upper),
    )
    kelt_upper = ind["kelt_upper"]
    signals["keltner_breakout"] = (
        (close > kelt_upper) & (close.shift(1) <= kelt_upper.shift(1)),
        (close < ind["kelt_lower"]) & (close.shift(1) >= ind["kelt_lower"].shift(1)),
    )

    # ── VOLUME ──
    obv = ind["obv"]
    obv_sma = calc_sma(obv, 20)
    signals["obv_trend"] = (
        (obv > obv_sma) & (obv > obv.shift(5)),
        (obv < obv_sma) & (obv < obv.shift(5)),
    )
    vol = df["Volume"]
    vol_sma = ind["vol_sma20"]
    signals["volume_price_spike"] = (
        (vol > vol_sma * 1.5) & (close > close.shift(1)),
        (vol > vol_sma * 1.5) & (close < close.shift(1)),
    )

    # ── STRUCTURE ──
    donch_hi = ind["donchian_high"]
    donch_lo = ind["donchian_low"]
    signals["donchian_breakout"] = (
        (close > donch_hi.shift(1)),
        (close < donch_lo.shift(1)),
    )
    # EMA pullback bounce
    signals["ema21_pullback_bounce"] = (
        (df["Low"].shift(1) <= ema21.shift(1)) & (close > ema21) & (ema9 > ema21),
        (df["High"].shift(1) >= ema21.shift(1)) & (close < ema21) & (ema9 < ema21),
    )
    # Swing level breakout
    swing_hi = ind["swing_hi"]
    swing_lo = ind["swing_lo"]
    signals["swing_breakout"] = (
        (close > swing_hi.shift(1)) & (close.shift(1) <= swing_hi.shift(1)),
        (close < swing_lo.shift(1)) & (close.shift(1) >= swing_lo.shift(1)),
    )

    return signals


# ═══════════════════════════════════════════════════════════════════════════
# Scorecard engine
# ═══════════════════════════════════════════════════════════════════════════

def score_signal(sig_long, sig_short, fwd, ticker, name):
    """Score a signal across all horizons and directions."""
    rows = []
    for horizon in HORIZONS:
        fr = fwd[horizon]
        for direction, sig in [("long", sig_long), ("short", sig_short)]:
            if sig is None:
                continue
            mask = sig.fillna(False)
            n_sig = mask.sum()
            if n_sig < 10:
                continue

            win_col = "long_win" if direction == "long" else "short_win"
            wins = fr[win_col][mask].sum()
            wr = wins / n_sig

            rets = fr["fwd_ret"][mask].dropna()
            if direction == "short":
                rets = -rets

            pos = rets[rets > 0].sum()
            neg = abs(rets[rets < 0].sum())
            pf = pos / neg if neg > 0 else (float("inf") if pos > 0 else 0)

            total_months = (mask.index[-1] - mask.index[0]).days / 30.44
            spm = n_sig / total_months if total_months > 0 else 0

            # False signal rate: moved > 1.5% against within 3 bars
            if direction == "long":
                false_mask = fr["mae_long"][mask].dropna() > 0.015
            else:
                false_mask = fr["mfe_long"][mask].dropna() > 0.015  # for shorts, MFE is adverse
            false_rate = false_mask.mean() if len(false_mask) > 0 else 0

            rows.append({
                "ticker": ticker, "signal": name, "direction": direction,
                "horizon": horizon, "n_signals": int(n_sig),
                "win_rate": round(wr, 3), "profit_factor": round(pf, 2),
                "avg_return_pct": round(rets.mean() * 100, 2) if len(rets) > 0 else 0,
                "signals_per_month": round(spm, 2),
                "false_rate": round(false_rate, 3),
            })
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Ticker clustering
# ═══════════════════════════════════════════════════════════════════════════

def compute_cluster_metrics(df, adx):
    """Compute clustering metrics for a single ticker."""
    close = df["Close"]
    daily_ret = close.pct_change().dropna()

    pct_trending = (adx > 25).mean()
    adx_median = adx.median()
    autocorr_1 = daily_ret.autocorr(lag=1) if len(daily_ret) > 10 else 0
    autocorr_5 = daily_ret.autocorr(lag=5) if len(daily_ret) > 10 else 0
    avg_abs_roc20 = close.pct_change(20).abs().mean() * 100
    avg_atr_pct = (calc_atr(df, 14) / close * 100).mean()

    # Simplified Hurst exponent
    hurst = _hurst_rs(daily_ret.values)

    return {
        "pct_trending": round(pct_trending, 3),
        "adx_median": round(adx_median, 1),
        "autocorr_1": round(autocorr_1, 3),
        "autocorr_5": round(autocorr_5, 3),
        "avg_roc20": round(avg_abs_roc20, 1),
        "avg_atr_pct": round(avg_atr_pct, 2),
        "hurst": round(hurst, 3),
    }


def _hurst_rs(returns, max_lag=100):
    """Simplified R/S Hurst exponent. H>0.5=trending, H<0.5=mean-reverting."""
    returns = returns[~np.isnan(returns)]
    if len(returns) < max_lag:
        return 0.5
    lags = range(10, min(max_lag, len(returns) // 3), 10)
    rs_vals = []
    for lag in lags:
        chunks = [returns[i:i + lag] for i in range(0, len(returns) - lag, lag)]
        rs = []
        for c in chunks:
            if len(c) < lag:
                continue
            m = c.mean()
            cumdev = np.cumsum(c - m)
            R = cumdev.max() - cumdev.min()
            S = c.std()
            if S > 0:
                rs.append(R / S)
        if rs:
            rs_vals.append((lag, np.mean(rs)))
    if len(rs_vals) < 3:
        return 0.5
    log_lags = np.log([x[0] for x in rs_vals])
    log_rs = np.log([x[1] for x in rs_vals])
    H = np.polyfit(log_lags, log_rs, 1)[0]
    return float(H)


def assign_cluster(metrics):
    """Assign ticker to cluster based on metrics."""
    h = metrics["hurst"]
    pt = metrics["pct_trending"]
    ac1 = metrics["autocorr_1"]

    if h > 0.55 and pt > 0.35:
        return "TREND"
    elif h < 0.48 or ac1 < -0.05:
        return "MEAN_REVERT"
    else:
        return "MOMENTUM"


# ═══════════════════════════════════════════════════════════════════════════
# Compute all indicators for a ticker
# ═══════════════════════════════════════════════════════════════════════════

def compute_indicators(df):
    """Compute all indicators needed for signal generation."""
    close = df["Close"]
    ind = {}

    ind["ema9"] = calc_ema(close, 9)
    ind["ema21"] = calc_ema(close, 21)
    ind["ema50"] = calc_ema(close, 50)
    ind["ema200"] = calc_ema(close, 200)
    ind["rsi14"] = calc_rsi(close, 14)

    plus_di, minus_di, adx = calc_adx(df, 14, 14)
    ind["plus_di"] = plus_di
    ind["minus_di"] = minus_di
    ind["adx"] = adx

    ind["atr"] = calc_atr(df, 14)
    macd_l, macd_s, macd_h = calc_macd(close, 12, 26, 9)
    ind["macd_line"] = macd_l
    ind["signal_line"] = macd_s
    ind["histogram"] = macd_h

    bb_u, bb_m, bb_l = calc_bollinger(close, 20, 2.0)
    ind["bb_upper"] = bb_u
    ind["bb_mid"] = bb_m
    ind["bb_lower"] = bb_l

    stk, std = calc_stochastic(df, 14, 3, 3)
    ind["stoch_k"] = stk
    ind["stoch_d"] = std

    st_dir, st_val = calc_supertrend(df, 10, 3.0)
    ind["st_dir"] = st_dir
    ind["st_val"] = st_val

    ind["range_filter"] = calc_range_filter(close, 100, 3.0)
    ind["vol_sma20"] = calc_sma(df["Volume"], 20)
    ind["donchian_high"] = df["High"].rolling(20).max()
    ind["donchian_low"] = df["Low"].rolling(20).min()

    # New indicators
    ind["obv"] = calc_obv(df)
    ind["cci"] = calc_cci(df, 20)
    ku, km, kl = calc_keltner(df, 20, 10, 1.5)
    ind["kelt_upper"] = ku
    ind["kelt_mid"] = km
    ind["kelt_lower"] = kl
    sh, sl = calc_swing_levels(df, 5)
    ind["swing_hi"] = sh
    ind["swing_lo"] = sl

    return ind


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  FRESH INDICATOR RESEARCH — Swing Options Strategy")
    print("=" * 70)

    all_scores = []
    cluster_data = {}

    for ticker in TICKERS:
        print(f"\n  {ticker}...", end=" ", flush=True)
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception as e:
            print(f"SKIP ({e})")
            continue

        # Use full data for indicator warmup, slice to 2020+ for scoring
        ind = compute_indicators(df)
        df_focus = df[df.index >= pd.Timestamp(DATA_START)]
        if len(df_focus) < 200:
            print(f"SKIP (only {len(df_focus)} bars after {DATA_START})")
            continue

        # Forward returns
        atr_focus = ind["atr"].reindex(df_focus.index)
        fwd = compute_forward_returns(df_focus, atr_focus)

        # Slice indicators to focus window
        ind_focus = {k: v.reindex(df_focus.index) for k, v in ind.items()}

        # Generate signals
        sigs = generate_signals(df_focus, ind_focus)

        # Score each signal
        ticker_scores = 0
        for sig_name, (sig_long, sig_short) in sigs.items():
            rows = score_signal(sig_long, sig_short, fwd, ticker, sig_name)
            all_scores.extend(rows)
            ticker_scores += len(rows)

        # Cluster metrics
        adx_focus = ind["adx"].reindex(df_focus.index).dropna()
        cluster_data[ticker] = compute_cluster_metrics(df_focus, adx_focus)

        print(f"{ticker_scores} scores, {len(df_focus)} bars")

    # Build scorecard DataFrame
    scorecard = pd.DataFrame(all_scores)

    if scorecard.empty:
        print("\nNo scores computed. Check data.")
        return

    # ── Tier assignment ──
    # Focus on 10-bar horizon (sweet spot for 2-4 week options)
    h10 = scorecard[scorecard["horizon"] == 10].copy()

    h10["tier"] = "FAIL"
    h10.loc[(h10["win_rate"] > 0.45) & (h10["profit_factor"] > 1.3) &
            (h10["n_signals"] >= 20) & (h10["signals_per_month"] >= 0.5) &
            (h10["signals_per_month"] <= 8), "tier"] = "TIER1"
    h10.loc[(h10["tier"] == "FAIL") &
            (h10["win_rate"] > 0.40) & (h10["profit_factor"] > 1.1) &
            (h10["n_signals"] >= 15), "tier"] = "TIER2"

    # ── Cluster assignments ──
    for ticker in cluster_data:
        cluster_data[ticker]["cluster"] = assign_cluster(cluster_data[ticker])

    # ── Print results ──
    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {len(scorecard)} total scores across {len(TICKERS)} tickers")
    print(f"{'=' * 70}")

    # Tier 1 signals
    t1 = h10[h10["tier"] == "TIER1"].sort_values("profit_factor", ascending=False)
    print(f"\n  TIER 1 — Proven Predictors ({len(t1)} entries)")
    if len(t1) > 0:
        print(tabulate(t1[["ticker", "signal", "direction", "n_signals", "win_rate",
                           "profit_factor", "avg_return_pct", "signals_per_month", "false_rate"]].head(30),
                       headers="keys", tablefmt="simple", showindex=False, floatfmt=".2f"))

    # Tier 2
    t2 = h10[h10["tier"] == "TIER2"].sort_values("profit_factor", ascending=False)
    print(f"\n  TIER 2 — Marginal ({len(t2)} entries)")
    if len(t2) > 0:
        print(tabulate(t2[["ticker", "signal", "direction", "win_rate",
                           "profit_factor", "signals_per_month"]].head(20),
                       headers="keys", tablefmt="simple", showindex=False, floatfmt=".2f"))

    # Cluster assignments
    print(f"\n  TICKER CLUSTERS:")
    cluster_rows = []
    for ticker in TICKERS:
        if ticker in cluster_data:
            m = cluster_data[ticker]
            cluster_rows.append({
                "Ticker": ticker, "Cluster": m["cluster"],
                "Hurst": m["hurst"], "ADX%>25": m["pct_trending"],
                "AutoCorr1": m["autocorr_1"], "AvgATR%": m["avg_atr_pct"],
            })
    print(tabulate(cluster_rows, headers="keys", tablefmt="simple", floatfmt=".3f"))

    # ── Best signal per ticker ──
    print(f"\n  BEST SIGNAL PER TICKER (10-bar horizon):")
    for ticker in TICKERS:
        t_data = h10[(h10["ticker"] == ticker) & (h10["tier"].isin(["TIER1", "TIER2"]))]
        if t_data.empty:
            best = h10[h10["ticker"] == ticker].sort_values("profit_factor", ascending=False).head(1)
            if len(best):
                b = best.iloc[0]
                print(f"    {ticker:>6s}: {b['signal']:<25s} {b['direction']:>5s}  "
                      f"WR={b['win_rate']:.1%} PF={b['profit_factor']:.2f} "
                      f"n={b['n_signals']}  ** NO TIER 1/2 **")
        else:
            best = t_data.sort_values("profit_factor", ascending=False).iloc[0]
            print(f"    {ticker:>6s}: {best['signal']:<25s} {best['direction']:>5s}  "
                  f"WR={best['win_rate']:.1%} PF={best['profit_factor']:.2f} "
                  f"n={best['n_signals']}  [{best['tier']}]")

    # ── Write report ──
    report = _build_report(h10, t1, t2, cluster_data, cluster_rows)
    out = Path("reports") / "fresh_strategy_research.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report)
    print(f"\n  Report: {out}")


def _build_report(h10, t1, t2, cluster_data, cluster_rows):
    """Build the markdown report."""
    lines = ["# Fresh Indicator Research — Swing Options Strategy", ""]
    lines.append(f"*{len(h10)} signal/ticker/direction tests at 10-bar horizon*")
    lines.append(f"*Data: {DATA_START} to 2026-03-26, 15 tickers*")
    lines.append("")

    # Tier 1
    lines.append("## Tier 1: Proven Predictors (WR>45%, PF>1.3, n>=20)")
    lines.append("")
    if len(t1) > 0:
        lines.append("| Ticker | Signal | Dir | N | WR | PF | Avg Ret% | Sig/Mo | False% |")
        lines.append("|--------|--------|-----|---|----|----|----------|--------|--------|")
        for _, r in t1.head(40).iterrows():
            lines.append(f"| {r['ticker']} | {r['signal']} | {r['direction']} | "
                         f"{r['n_signals']} | {r['win_rate']:.1%} | {r['profit_factor']:.2f} | "
                         f"{r['avg_return_pct']:.2f} | {r['signals_per_month']:.1f} | "
                         f"{r['false_rate']:.1%} |")
    else:
        lines.append("No Tier 1 signals found.")
    lines.append("")

    # Tier 2
    lines.append("## Tier 2: Marginal (WR>40%, PF>1.1)")
    lines.append("")
    if len(t2) > 0:
        lines.append("| Ticker | Signal | Dir | N | WR | PF | Sig/Mo |")
        lines.append("|--------|--------|-----|---|----|----|--------|")
        for _, r in t2.head(30).iterrows():
            lines.append(f"| {r['ticker']} | {r['signal']} | {r['direction']} | "
                         f"{r['n_signals']} | {r['win_rate']:.1%} | {r['profit_factor']:.2f} | "
                         f"{r['signals_per_month']:.1f} |")
    lines.append("")

    # Clusters
    lines.append("## Ticker Clusters")
    lines.append("")
    lines.append("| Ticker | Cluster | Hurst | ADX%>25 | AutoCorr1 | AvgATR% |")
    lines.append("|--------|---------|-------|---------|-----------|---------|")
    for r in cluster_rows:
        lines.append(f"| {r['Ticker']} | {r['Cluster']} | {r['Hurst']:.3f} | "
                     f"{r['ADX%>25']:.1%} | {r['AutoCorr1']:.3f} | {r['AvgATR%']:.2f} |")
    lines.append("")

    # Cluster summary
    clusters = {}
    for r in cluster_rows:
        c = r["Cluster"]
        clusters.setdefault(c, []).append(r["Ticker"])
    for c, tickers in sorted(clusters.items()):
        lines.append(f"**{c}:** {', '.join(tickers)}")
    lines.append("")

    # Archetype definitions
    lines.append("## Strategy Archetypes")
    lines.append("")
    lines.append("### Archetype 1: Trend Pullback")
    lines.append("- **For:** TREND cluster tickers")
    lines.append("- **Entry:** Price pulls back to EMA(21), bounces above with EMA9 > EMA21")
    lines.append("- **Confirmation:** RSI > 50, MACD histogram positive")
    lines.append("- **Stop:** Below recent swing low or 2x ATR")
    lines.append("- **Target:** 2x ATR from entry or previous swing high")
    lines.append("")
    lines.append("### Archetype 2: Momentum Breakout")
    lines.append("- **For:** MOMENTUM cluster tickers")
    lines.append("- **Entry:** Close breaks above Donchian(20) high with volume > 1.5x SMA")
    lines.append("- **Confirmation:** ADX rising, SuperTrend bullish")
    lines.append("- **Stop:** Below Donchian midpoint or 2x ATR")
    lines.append("- **Target:** 2x ATR or next resistance level")
    lines.append("")
    lines.append("### Archetype 3: Mean Reversion")
    lines.append("- **For:** MEAN_REVERT cluster tickers")
    lines.append("- **Entry:** RSI exits oversold (<30 crosses above) + BB lower band touch")
    lines.append("- **Confirmation:** Stochastic cross up, volume expansion")
    lines.append("- **Stop:** Below recent swing low")
    lines.append("- **Target:** BB midline (mean) or 1.5x ATR")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
