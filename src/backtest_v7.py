#!/usr/bin/env python3
"""
V7 Backtest — V4 signal engine + V6 evidence-weighted composite overlay.

Runs on 12 tickers: SPY, QQQ, NVDA, INTC, TSLA, AMD, AMZN, JNJ, MSFT, SOFI, IWM, XLF
"""

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicators import calc_ema, calc_rsi, calc_adx, calc_atr, calc_macd, calc_sma
from validate_pinescript import compute_weekly_indicators, V6Trade, _calc_qty

TICKERS = ["SPY", "QQQ", "NVDA", "INTC", "TSLA", "AMD", "AMZN", "JNJ", "MSFT", "SOFI", "IWM", "XLF"]

# V7 defaults (matching Pine Script)
P = {
    "min_score": 75, "cooldown": 5, "long_only": True, "short_min": 85,
    "adx_trend": 25, "adx_range": 20, "chop_len": 14,
    "s1_oversold": 30, "s1_overbought": 70,
    "s2_donch": 20, "s2_sma": 50, "s2_vol_mult": 1.3,
    "s3_fast": 9, "s3_slow": 21, "s3_trend": 50,
    "s4_wk_fast": 20, "s4_wk_slow": 50, "s4_daily_ema": 21, "s4_rsi_lo": 40, "s4_rsi_hi": 60,
    "atr_min_pct": 0.8, "atr_max_pct": 6.0,
    "rsi_exit": 80, "max_hold": 20, "ema_exit_bars": 2,
    "capital": 50_000.0, "qty_pct": 0.10, "commission": 3.0,
}


def simulate_v7(df: pd.DataFrame) -> list[V6Trade]:
    """Run V7 bar-by-bar simulation."""
    n = len(df)
    if n < 300:
        return []
    close = df["Close"]

    # ── Indicators ──
    ema9 = calc_ema(close, P["s3_fast"])
    ema21 = calc_ema(close, P["s3_slow"])
    ema50 = calc_ema(close, P["s3_trend"])
    sma200 = calc_sma(close, 200)
    ema200 = calc_ema(close, 200)
    s4_dema = calc_ema(close, P["s4_daily_ema"])
    rsi = calc_rsi(close, 14)
    plus_di, minus_di, adx = calc_adx(df, 14, 14)
    atr = calc_atr(df, 14)
    atr_pct = atr / close * 100
    atr_sma50 = calc_sma(atr, 50)
    macd_l, macd_s, macd_h = calc_macd(close, 12, 26, 9)
    vol_sma20 = calc_sma(df["Volume"], 20)
    donch_hi = df["High"].rolling(P["s2_donch"]).max()
    donch_lo = df["Low"].rolling(P["s2_donch"]).min()

    # Choppiness
    from indicators import _true_range
    tr = _true_range(df)
    chop_sum = tr.rolling(P["chop_len"]).sum()
    chop_hl = df["High"].rolling(P["chop_len"]).max() - df["Low"].rolling(P["chop_len"]).min()
    chop = 100 * np.log10(chop_sum / chop_hl.replace(0, np.nan)) / math.log10(P["chop_len"])

    # BB width
    bb_mid = calc_sma(close, 20)
    bb_std = close.rolling(20).std(ddof=0)
    bb_up = bb_mid + 2 * bb_std
    bb_lo = bb_mid - 2 * bb_std
    bbw = (bb_up - bb_lo) / bb_mid.replace(0, np.nan) * 100
    bbw_sma = calc_sma(bbw, 50)

    # ROC
    roc20 = close.pct_change(20) * 100
    roc60 = close.pct_change(60) * 100

    # 52-week
    hi52 = df["High"].rolling(252, min_periods=50).max()
    lo52 = df["Low"].rolling(252, min_periods=50).min()
    range52 = (hi52 - lo52).replace(0, np.nan)
    dist_hi = (hi52 - close) / range52 * 100
    dist_lo = (close - lo52) / range52 * 100

    # Weekly
    wk = compute_weekly_indicators(df)
    wk_bullish = ((wk["wk_ema9"] > wk["wk_ema21"]) & (wk["wk_close"] > wk["wk_ema200"])).fillna(False)

    # S4 weekly EMAs (using 20/50)
    weekly = df.resample("W-FRI").agg({"Close": "last"}).dropna()
    s4_wk_fast = calc_ema(weekly["Close"], P["s4_wk_fast"])
    s4_wk_slow = calc_ema(weekly["Close"], P["s4_wk_slow"])
    s4_wk_data = pd.DataFrame({"f": s4_wk_fast, "s": s4_wk_slow, "c": weekly["Close"]})
    s4_wk = s4_wk_data.reindex(df.index, method="ffill")
    s4_wk_bull = (s4_wk["f"] > s4_wk["s"]) & (s4_wk["c"] > s4_wk["f"])
    s4_wk_bull = s4_wk_bull.fillna(False)

    # Weekly ADX proxy
    wk_adx_raw = pd.Series(np.nan, index=weekly.index)  # simplified: use daily ADX avg per week
    wk_adx_daily = adx.resample("W-FRI").last()
    s4_wk_strong = (wk_adx_daily.reindex(df.index, method="ffill").fillna(0) > 20)

    # EMA cross events
    ema9_above = ema9 > ema21
    s3_cross_up = ema9_above & ~ema9_above.shift(1).fillna(False)
    s3_cross_dn = ~ema9_above & ema9_above.shift(1).fillna(True)

    # S4 triggers
    s4_pb_buy = (rsi < P["s4_rsi_lo"]) & (rsi > 25)
    s4_bounce = (close > s4_dema) & (close.shift(1) <= s4_dema.shift(1))
    s4_pb_sell = (rsi > P["s4_rsi_hi"]) & (rsi < 75)
    s4_reject = (close < s4_dema) & (close.shift(1) >= s4_dema.shift(1))

    # Vol
    vol_above = df["Volume"] > vol_sma20 * 1.15
    vol_spike = df["Volume"] > vol_sma20 * P["s2_vol_mult"]
    atr_expanding = atr > atr_sma50 * 1.2
    bbw_expanding = bbw > bbw_sma * 1.1
    bbw_contracting = bbw < bbw_sma * 0.9

    # S2 SMA
    s2_sma = calc_sma(close, P["s2_sma"])

    # S3 anchor
    s3_anchor = calc_sma(close, 20)

    dates = df.index
    trades: list[V6Trade] = []
    in_pos = False
    pending = False
    pend_mode = ""
    pend_score = 0.0
    pend_dir = ""
    entry_bar = 0
    entry_price = 0.0
    last_sig = -P["cooldown"] - 1
    below_ct = 0

    for i in range(1, n):
        c = close.iat[i]
        if np.isnan(ema200.iat[i]) or np.isnan(adx.iat[i]) or np.isnan(rsi.iat[i]):
            continue

        # Enter pending
        if pending and not in_pos:
            entry_price = df["Open"].iat[i] + 0.01
            in_pos = True
            entry_bar = i
            below_ct = 0
            pending = False

        # Exit checks
        if in_pos:
            bh = i - entry_bar
            if c < ema21.iat[i]:
                below_ct += 1
            else:
                below_ct = 0

            ex = ""
            if below_ct >= P["ema_exit_bars"]:
                ex = "stop_loss"
            elif rsi.iat[i] > P["rsi_exit"]:
                ex = "take_profit"
            elif bh >= P["max_hold"]:
                ex = "time_stop"
            # Regime change: mean-rev with high confidence
            elif not np.isnan(chop.iat[i]):
                mr_score = 0.0
                if adx.iat[i] < P["adx_range"]:
                    mr_score += min((P["adx_range"] - adx.iat[i]) / 10, 1) * 50
                if chop.iat[i] > 61.8:
                    mr_score += min((chop.iat[i] - 61.8) / 20, 1) * 50
                if mr_score > 60:
                    ex = "regime_change"

            if ex:
                qty = min(_calc_qty(entry_price, P["capital"], P["qty_pct"]), 500)
                if pend_dir == "BUY":
                    pnl = (c - entry_price) * qty - P["commission"]
                else:
                    pnl = (entry_price - c) * qty - P["commission"]
                trades.append(V6Trade(dates[entry_bar], dates[i], entry_price, c,
                                      round(pnl, 2), pend_mode, ex, pend_score, bh))
                in_pos = False
                last_sig = i
                continue

        if in_pos:
            continue
        if i - last_sig < P["cooldown"]:
            continue
        if np.isnan(atr_pct.iat[i]) or atr_pct.iat[i] < P["atr_min_pct"] or atr_pct.iat[i] > P["atr_max_pct"]:
            continue

        # ── V4 Regime (5-state continuous scoring) ──
        ts = min(((adx.iat[i] - P["adx_trend"]) / 15 if adx.iat[i] > P["adx_trend"] else 0) +
                 ((38.2 - chop.iat[i]) / 20 if not np.isnan(chop.iat[i]) and chop.iat[i] < 38.2 else 0), 1) * 100
        bs = min((0.4 if atr_expanding.iat[i] else 0) +
                 (0.4 if not np.isnan(bbw_expanding.iat[i]) and bbw_expanding.iat[i] else 0) +
                 (0.2 if adx.iat[i] > P["adx_range"] else 0), 1) * 100
        mrs = min(((P["adx_range"] - adx.iat[i]) / 10 if adx.iat[i] < P["adx_range"] else 0) +
                  ((chop.iat[i] - 61.8) / 20 if not np.isnan(chop.iat[i]) and chop.iat[i] > 61.8 else 0) +
                  (0.3 if not np.isnan(bbw_contracting.iat[i]) and bbw_contracting.iat[i] else 0), 1) * 100
        mms = min((0.5 if P["adx_range"] < adx.iat[i] <= P["adx_trend"] else 0) +
                  (0.3 if not np.isnan(bbw_expanding.iat[i]) and not bbw_expanding.iat[i] and not np.isnan(bbw_contracting.iat[i]) and not bbw_contracting.iat[i] else 0) +
                  (0.2 if not np.isnan(roc20.iat[i]) and abs(roc20.iat[i]) > 3 else 0), 1) * 100

        r_trend = ts >= 60
        r_brk = bs >= 60
        r_mr = mrs >= 60
        r_mom = mms >= 40 and not r_brk and not r_trend and not r_mr
        regime = 2 if r_brk else (4 if r_trend else (3 if r_mom else (1 if r_mr else 0)))

        # Alignment
        s1_ok = regime in (1, 0, 3)
        s2_ok = regime in (2, 0, 4)
        s3_ok = regime in (3, 0, 4, 2)
        s4_ok = regime in (4, 0, 3)

        # ── S1 Score ──
        r_val = rsi.iat[i]
        s1L = 0.0
        s1_rs = (35 if r_val < P["s1_oversold"] - 10 else
                 30 if r_val < P["s1_oversold"] - 5 else
                 25 if r_val < P["s1_oversold"] else
                 12 if r_val < P["s1_oversold"] + 5 else 0)
        if s1_rs > 0:
            trend_up = wk_bullish.iat[i] and c > sma200.iat[i] if not np.isnan(sma200.iat[i]) else False
            s1L = s1_rs
            s1L += 25 if trend_up else (15 if not np.isnan(sma200.iat[i]) and c > sma200.iat[i] else (12 if r_val < P["s1_oversold"] - 5 else 0))
            s1L += 15 if vol_above.iat[i] else 0
            s1L += 10 if not np.isnan(dist_hi.iat[i]) and dist_hi.iat[i] > 50 else (5 if not np.isnan(dist_hi.iat[i]) and dist_hi.iat[i] > 30 else 0)
            s1L += 15 if r_mr else (8 if regime == 0 else 0)
        s1L = s1L if s1_ok else 0

        # ── S2 Score ──
        s2L = 0.0
        brk_hi = not np.isnan(donch_hi.iat[i - 1]) and c > donch_hi.iat[i - 1]
        ext_up = not np.isnan(s2_sma.iat[i]) and c > s2_sma.iat[i] + atr.iat[i] * 1.5
        has_vol = vol_spike.iat[i] or vol_above.iat[i]
        if brk_hi and not ext_up and has_vol:
            s2L = 30
            s2L += 15 if not np.isnan(s2_sma.iat[i]) and c > s2_sma.iat[i] else 0
            s2L += 15 if adx.iat[i] > P["adx_trend"] else (8 if adx.iat[i] > P["adx_range"] else 0)
            s2L += 20 if vol_spike.iat[i] else 10
            s2L += 5 if atr_expanding.iat[i] else 0
            s2L += 15 if r_brk else (8 if regime == 4 else (5 if regime == 0 else 0))
        s2L = s2L if s2_ok else 0

        # ── S3 Score ──
        s3L = 0.0
        blocked = r_val > 70
        recent_up = any(s3_cross_up.iat[max(0, i - j)] for j in range(6) if i - j >= 0 and not np.isnan(s3_cross_up.iat[max(0, i - j)]))
        if not blocked and recent_up:
            s3L = 25 if s3_cross_up.iat[i] else (10 if ema9.iat[i] > ema21.iat[i] else 0)
            s3L += 15 if not np.isnan(s3_anchor.iat[i]) and c > s3_anchor.iat[i] else 0
            s3L += 12 if not np.isnan(ema50.iat[i]) and c > ema50.iat[i] else 0
            s3L += 15 if macd_h.iat[i] > 0 and r_val > 50 else (8 if macd_h.iat[i] > 0 else 0)
            s3L += 10 if vol_above.iat[i] else 0
            s3L += 8 if not np.isnan(roc20.iat[i]) and roc20.iat[i] > 3 else 0
            s3L += 15 if r_mom else (10 if regime == 4 else (8 if regime == 2 else (5 if regime == 0 else 0)))
        s3L = s3L if s3_ok else 0

        # ── S4 Score ──
        s4L = 0.0
        has_entry = s4_pb_buy.iat[i] or s4_bounce.iat[i]
        if has_entry:
            s4L = 25 if s4_wk_bull.iat[i] else 0
            s4L += 10 if s4_wk_strong.iat[i] else 0
            s4L += 20 if s4_pb_buy.iat[i] else (15 if s4_bounce.iat[i] else 0)
            s4L += 8 if macd_l.iat[i] > macd_s.iat[i] else 0
            s4L += 8 if not np.isnan(sma200.iat[i]) and c > sma200.iat[i] else 0
            s4L += 7 if vol_above.iat[i] else 0
            s4L += 7 if not np.isnan(roc60.iat[i]) and roc60.iat[i] > 5 else 0
            s4L += 15 if r_trend else (10 if regime == 3 else (5 if regime == 0 else 0))
        s4L = s4L if s4_ok else 0

        # Winner
        scores = [s1L, s2L, s3L, s4L]
        best = max(scores)
        if best <= 0:
            continue
        strat = scores.index(best) + 1  # 1-indexed
        direction = "BUY"  # long-only for now

        # ── V6 Composite ──
        comp = 0.0
        comp += 25 if ema9.iat[i] > ema21.iat[i] else 0
        comp += 25 if r_val > 50 else 0
        comp += 20 if not np.isnan(ema200.iat[i]) and c > ema200.iat[i] else 0
        comp += 15 if wk_bullish.iat[i] else 0
        comp += 5 if vol_above.iat[i] else 0
        comp += 5 if macd_h.iat[i] > 0 else 0
        comp += 5 if adx.iat[i] > P["adx_trend"] else 0

        # Long-only filter
        if P["long_only"] and direction != "BUY":
            continue

        # Promotion gate
        if comp < P["min_score"]:
            continue

        pending = True
        pend_mode = f"S{strat}"
        pend_score = comp
        pend_dir = direction
        last_sig = i

    # Close open position
    if in_pos:
        qty = min(_calc_qty(entry_price, P["capital"], P["qty_pct"]), 500)
        pnl = (close.iat[-1] - entry_price) * qty - P["commission"]
        trades.append(V6Trade(dates[entry_bar], dates[-1], entry_price, close.iat[-1],
                              round(pnl, 2), pend_mode, "end_of_data", pend_score, n - 1 - entry_bar))
    return trades


def main():
    print("=" * 70)
    print("  V7 BACKTEST — V4 Signals + V6 Intelligence Filter")
    print("=" * 70)

    rows = []
    strat_counts = {"S1": 0, "S2": 0, "S3": 0, "S4": 0}
    all_trades = []

    for ticker in TICKERS:
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception:
            print(f"  {ticker}: data not found")
            continue

        trades = simulate_v7(df)
        all_trades.extend(trades)

        nt = len(trades)
        if nt == 0:
            rows.append({"Ticker": ticker, "Trades": 0, "WR%": 0, "PF": 0,
                         "Net PnL": 0, "Sharpe": 0, "Avg Bars": 0, "Sig/Yr": 0})
            continue

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        gp = sum(t.pnl for t in wins)
        gl = abs(sum(t.pnl for t in losses))
        pf = gp / gl if gl > 0 else float("inf")
        wr = 100 * len(wins) / nt
        net = sum(t.pnl for t in trades)
        pnls = np.array([t.pnl for t in trades])
        avg_bars = np.mean([t.bars_held for t in trades])
        sharpe = pnls.mean() / pnls.std() * np.sqrt(252 / max(1, avg_bars)) if pnls.std() > 0 else 0

        years = (df.index[-1] - df.index[0]).days / 365.25
        sig_yr = nt / years if years > 0 else 0

        for t in trades:
            if t.mode in strat_counts:
                strat_counts[t.mode] += 1

        rows.append({
            "Ticker": ticker, "Trades": nt, "WR%": round(wr, 1),
            "PF": round(pf, 2), "Net PnL": round(net, 0),
            "Sharpe": round(sharpe, 2), "Avg Bars": round(avg_bars, 1),
            "Sig/Yr": round(sig_yr, 1),
        })

    print()
    print(tabulate(rows, headers="keys", tablefmt="simple", floatfmt=".1f"))

    # Aggregate
    total = len(all_trades)
    if total > 0:
        total_pnl = sum(t.pnl for t in all_trades)
        total_wins = sum(1 for t in all_trades if t.pnl > 0)
        gp = sum(t.pnl for t in all_trades if t.pnl > 0)
        gl = abs(sum(t.pnl for t in all_trades if t.pnl <= 0))
        print(f"\n  Portfolio: {total} trades, ${total_pnl:,.0f} net, "
              f"{100*total_wins/total:.1f}% WR, PF {gp/gl:.2f}" if gl > 0 else "")

    # Strategy breakdown
    print(f"\n  Strategy breakdown:")
    for s, c in sorted(strat_counts.items()):
        print(f"    {s}: {c} signals ({100*c/total:.0f}%)" if total > 0 else f"    {s}: 0")

    # Exit breakdown
    exit_types = {}
    for t in all_trades:
        exit_types[t.exit_reason] = exit_types.get(t.exit_reason, 0) + 1
    print(f"\n  Exit breakdown:")
    for ex, ct in sorted(exit_types.items(), key=lambda x: -x[1]):
        avg_pnl = np.mean([t.pnl for t in all_trades if t.exit_reason == ex])
        print(f"    {ex:<15s}: {ct:>4d} ({100*ct/total:.0f}%)  avg PnL ${avg_pnl:>8.0f}")


if __name__ == "__main__":
    main()
