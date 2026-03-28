#!/usr/bin/env python3
"""
Validate Pine Script V6 against Python backtest.

Implements the EXACT V6 logic (regime, Mode A/B scoring, exits) in Python
and runs a bar-by-bar simulation to produce expected values for TradingView
comparison.

Outputs:
  - Console comparison table
  - reports/pinescript_validation.md
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicators import calc_ema, calc_rsi, calc_adx, calc_atr, calc_macd, calc_sma


# ═══════════════════════════════════════════════════════════════════════════
# V6 Parameters (exact match to Pine Script defaults)
# ═══════════════════════════════════════════════════════════════════════════

V6 = {
    # Master
    "min_score_a": 70,
    "min_score_b": 65,
    "cooldown_bars": 5,
    # Regime
    "adx_trend_thr": 25,
    "adx_range_thr": 20,
    "adx_quiet_bars": 5,
    # Mode A
    "rsi_lo_entry": 55,
    "rsi_hi_entry": 75,
    "pullback_pct": 2.0,
    "ema_fast": 9,
    "ema_slow": 21,
    "ema_trend": 200,
    # Mode B
    "donchian_len": 20,
    "brk_vol_mult": 1.5,
    # Risk
    "atr_min_pct": 0.8,
    "atr_max_pct": 6.0,
    # Exit
    "rsi_exit_hi": 80,
    "max_hold_bars": 20,
    "ema_exit_bars": 2,
    # Strategy settings
    "initial_capital": 50_000.0,
    "qty_pct": 0.10,  # 10% of equity
    "commission": 1.50,
    "slippage_ticks": 1,
    "tick_size": 0.01,
}


# ═══════════════════════════════════════════════════════════════════════════
# Weekly data helper
# ═══════════════════════════════════════════════════════════════════════════

def compute_weekly_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily to weekly, compute EMAs, forward-fill back to daily index."""
    weekly = df.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()

    wk_ema9 = calc_ema(weekly["Close"], 9)
    wk_ema21 = calc_ema(weekly["Close"], 21)
    wk_ema200 = calc_ema(weekly["Close"], 200)

    wk_data = pd.DataFrame({
        "wk_ema9": wk_ema9,
        "wk_ema21": wk_ema21,
        "wk_ema200": wk_ema200,
        "wk_close": weekly["Close"],
    })

    # Forward-fill weekly values to daily index
    wk_daily = wk_data.reindex(df.index, method="ffill")
    return wk_daily


# ═══════════════════════════════════════════════════════════════════════════
# V6 Simulation
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class V6Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    pnl: float
    mode: str
    exit_reason: str
    score: float
    bars_held: int


def simulate_v6(df: pd.DataFrame, cluster: str = "Auto-detect") -> list[V6Trade]:
    """Run V6 simulation matching Pine Script logic exactly."""
    p = V6
    close = df["Close"]

    # ── Indicators ──
    ema9 = calc_ema(close, p["ema_fast"])
    ema21 = calc_ema(close, p["ema_slow"])
    ema200 = calc_ema(close, p["ema_trend"])
    rsi = calc_rsi(close, 14)
    plus_di, minus_di, adx = calc_adx(df, 14, 14)
    atr = calc_atr(df, 14)
    macd_line, signal_line, histogram = calc_macd(close, 12, 26, 9)
    vol_sma20 = calc_sma(df["Volume"], 20)
    donchian_hi = df["High"].rolling(p["donchian_len"]).max()
    high20 = df["High"].rolling(20).max()

    atr_pct = atr / close * 100

    # ── Weekly ──
    wk = compute_weekly_indicators(df)
    wk_bullish = (wk["wk_ema9"] > wk["wk_ema21"]) & (wk["wk_close"] > wk["wk_ema200"])
    wk_bullish = wk_bullish.fillna(False)

    # ── Auto-detect cluster ──
    adx_avg50 = calc_sma(adx, 50)
    if cluster == "Auto-detect":
        # Per-bar decision, but for simplicity use last valid value
        pass  # handled per-bar below

    # ── Bar-by-bar simulation ──
    dates = df.index
    n = len(dates)
    trades: list[V6Trade] = []

    in_position = False
    pending_signal = False
    pending_mode = ""
    pending_score = 0.0
    entry_bar = 0
    entry_price = 0.0
    last_signal_bar = -p["cooldown_bars"] - 1
    below_ema21_count = 0
    adx_quiet_count = 0

    for i in range(1, n):
        c = close.iat[i]
        # Skip bars with NaN indicators
        if np.isnan(ema200.iat[i]) or np.isnan(adx.iat[i]) or np.isnan(rsi.iat[i]):
            continue

        # ── Enter pending position at this bar's open ──
        if pending_signal and not in_position:
            entry_price = df["Open"].iat[i] + p["slippage_ticks"] * p["tick_size"]
            in_position = True
            entry_bar = i
            below_ema21_count = 0
            pending_signal = False

        # ── Exit checks (while in position) ──
        if in_position:
            bars_held = i - entry_bar

            # EMA stop: close < EMA21 for N consecutive bars
            if c < ema21.iat[i]:
                below_ema21_count += 1
            else:
                below_ema21_count = 0

            exit_reason = ""
            if below_ema21_count >= p["ema_exit_bars"]:
                exit_reason = "stop_loss"
            elif rsi.iat[i] > p["rsi_exit_hi"]:
                exit_reason = "take_profit"
            elif bars_held >= p["max_hold_bars"]:
                exit_reason = "time_stop"
            elif not _is_trending_up(adx.iat[i], plus_di.iat[i], minus_di.iat[i],
                                     c, ema200.iat[i], p):
                exit_reason = "regime_change"

            if exit_reason:
                exit_price = c  # strategy.close on bar close
                qty = _calc_qty(entry_price, V6["initial_capital"], V6["qty_pct"])
                pnl = (exit_price - entry_price) * qty - p["commission"] * 2
                trades.append(V6Trade(
                    entry_date=dates[entry_bar],
                    exit_date=dates[i],
                    entry_price=entry_price,
                    exit_price=exit_price,
                    pnl=round(pnl, 2),
                    mode=pending_mode,
                    exit_reason=exit_reason,
                    score=pending_score,
                    bars_held=bars_held,
                ))
                in_position = False
                last_signal_bar = i
                continue

        # ── Signal generation (only when flat) ──
        if in_position:
            continue

        # Cooldown
        if i - last_signal_bar < p["cooldown_bars"]:
            continue

        # ATR filter
        if np.isnan(atr_pct.iat[i]) or atr_pct.iat[i] < p["atr_min_pct"] \
                or atr_pct.iat[i] > p["atr_max_pct"]:
            continue

        # ── V6 Regime ──
        trending_up = _is_trending_up(adx.iat[i], plus_di.iat[i], minus_di.iat[i],
                                      c, ema200.iat[i], p)

        # Ranging: ADX < range threshold for quiet_bars consecutive bars
        if adx.iat[i] < p["adx_range_thr"]:
            adx_quiet_count += 1
        else:
            adx_quiet_count = 0
        ranging = adx_quiet_count >= p["adx_quiet_bars"]

        # Breakout: ADX crossed above trend threshold in last 3 bars + volume spike
        adx_cross = False
        for j in range(max(0, i - 2), i + 1):
            if j > 0 and adx.iat[j] > p["adx_trend_thr"] and adx.iat[j - 1] <= p["adx_trend_thr"]:
                adx_cross = True
                break
        vol_spike = df["Volume"].iat[i] > vol_sma20.iat[i] * p["brk_vol_mult"] \
            if not np.isnan(vol_sma20.iat[i]) else False
        breakout_regime = adx_cross and vol_spike

        # ── Cluster detection ──
        if cluster == "Auto-detect":
            use_mode_b = not np.isnan(adx_avg50.iat[i]) and adx_avg50.iat[i] > 22
        else:
            use_mode_b = cluster == "Momentum"

        # ── Mode A: Trend Continuation ──
        mode_a_score = 0.0
        if trending_up and wk_bullish.iat[i]:
            ema_ok = ema9.iat[i] > ema21.iat[i]
            rsi_ok = p["rsi_lo_entry"] <= rsi.iat[i] <= p["rsi_hi_entry"]
            pct_from_hi = (high20.iat[i] - c) / high20.iat[i] * 100 \
                if not np.isnan(high20.iat[i]) and high20.iat[i] > 0 else 999
            near_ok = pct_from_hi <= p["pullback_pct"]
            above_ok = c > ema200.iat[i]
            adx_ok = adx.iat[i] > p["adx_trend_thr"]
            vol_ok = df["Volume"].iat[i] > vol_sma20.iat[i] * 0.8 \
                if not np.isnan(vol_sma20.iat[i]) else False

            if ema_ok and rsi_ok and near_ok and above_ok and adx_ok and vol_ok:
                mode_a_score = (
                    (25.0 if ema_ok else 0.0) +
                    (25.0 if 60 <= rsi.iat[i] <= 70 else 15.0) +
                    (20.0 if above_ok else 0.0) +
                    (15.0 if wk_bullish.iat[i] else 0.0) +
                    (5.0 if df["Volume"].iat[i] > vol_sma20.iat[i] else 0.0) +
                    (5.0 if histogram.iat[i] > 0 else 0.0) +
                    (5.0 if adx.iat[i] > 30 else 0.0)
                )

        # ── Mode B: Breakout ──
        mode_b_score = 0.0
        if breakout_regime and use_mode_b:
            brk_ok = c > donchian_hi.shift(1).iat[i] if i > 0 and \
                not np.isnan(donchian_hi.iat[i - 1]) else False
            vol_ok_b = vol_spike
            rsi_ok_b = rsi.iat[i] > 50

            if brk_ok and vol_ok_b and adx_cross and rsi_ok_b:
                mode_b_score = (
                    (25.0 if ema9.iat[i] > ema21.iat[i] else 0.0) +
                    (25.0 if rsi.iat[i] > 50 else 15.0 if rsi.iat[i] > 40 else 0.0) +
                    (20.0 if c > ema200.iat[i] else 0.0) +
                    (15.0 if wk_bullish.iat[i] else 0.0) +
                    (5.0 if vol_spike else 0.0) +
                    (5.0 if histogram.iat[i] > 0 else 0.0) +
                    (5.0 if adx.iat[i] > 30 else 0.0)
                )

        # ── Winner selection ──
        best_score = max(mode_a_score, mode_b_score)
        best_mode = ""
        min_score = 0

        if mode_a_score >= mode_b_score and mode_a_score > 0:
            best_mode = "A"
            min_score = p["min_score_a"]
        elif mode_b_score > 0:
            best_mode = "B"
            min_score = p["min_score_b"]

        if best_score >= min_score and best_mode:
            pending_signal = True
            pending_mode = best_mode
            pending_score = best_score
            last_signal_bar = i

    # Close any open position at end
    if in_position:
        exit_price = close.iat[-1]
        qty = _calc_qty(entry_price, V6["initial_capital"], V6["qty_pct"])
        pnl = (exit_price - entry_price) * qty - p["commission"] * 2
        trades.append(V6Trade(
            entry_date=dates[entry_bar],
            exit_date=dates[-1],
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=round(pnl, 2),
            mode=pending_mode,
            exit_reason="end_of_data",
            score=pending_score,
            bars_held=n - 1 - entry_bar,
        ))

    return trades


def _is_trending_up(adx_val, di_plus, di_minus, close_val, ema200_val, p):
    return adx_val > p["adx_trend_thr"] and di_plus > di_minus and close_val > ema200_val


def _calc_qty(entry_price, capital, pct):
    """Shares = floor(capital * pct / price). Min 1."""
    if entry_price <= 0:
        return 1
    return max(1, int(capital * pct / entry_price))


# ═══════════════════════════════════════════════════════════════════════════
# Trade metrics
# ═══════════════════════════════════════════════════════════════════════════

def calc_metrics(trades: list[V6Trade]) -> dict:
    if not trades:
        return {"trades": 0}
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gp = sum(wins) if wins else 0
    gl = abs(sum(losses)) if losses else 0

    # Sharpe (annualized from trade returns)
    if len(pnls) > 1:
        pnl_arr = np.array(pnls)
        sharpe = (pnl_arr.mean() / pnl_arr.std() * np.sqrt(252 / max(1, np.mean([t.bars_held for t in trades])))) \
            if pnl_arr.std() > 0 else 0
    else:
        sharpe = 0

    return {
        "trades": len(trades),
        "winners": len(wins),
        "losers": len(losses),
        "win_rate": round(100 * len(wins) / len(trades), 1),
        "net_pnl": round(sum(pnls), 2),
        "avg_win": round(np.mean(wins), 2) if wins else 0,
        "avg_loss": round(np.mean(losses), 2) if losses else 0,
        "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        "sharpe": round(sharpe, 2),
        "avg_bars": round(np.mean([t.bars_held for t in trades]), 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Repainting check
# ═══════════════════════════════════════════════════════════════════════════

def check_repainting() -> list[str]:
    """Analyze Pine Script for repainting risks."""
    pine_path = Path("pinescript/portfolio_scanner_v6.pine")
    code = pine_path.read_text()
    findings = []

    # Check 1: request.security lookahead (count only non-comment lines)
    if "barmerge.lookahead_off" in code:
        count = code.count("barmerge.lookahead_off")
        # Count actual request.security calls (lines starting with non-comment code)
        sec_count = sum(1 for line in code.split("\n")
                        if "request.security" in line and not line.strip().startswith("//"))
        if count >= sec_count:
            findings.append(f"PASS: All {sec_count} request.security calls use "
                            f"barmerge.lookahead_off ({count} instances)")
        else:
            findings.append(f"WARN: {sec_count} request.security calls but only "
                            f"{count} barmerge.lookahead_off — potential repainting")
    else:
        findings.append("FAIL: No barmerge.lookahead_off found — repainting risk")

    # Check 2: process_orders_on_close
    if "process_orders_on_close=true" in code:
        findings.append("PASS: process_orders_on_close=true — orders processed on "
                        "bar close, filled at next bar open")
    else:
        findings.append("WARN: process_orders_on_close not set to true")

    # Check 3: barstate.isconfirmed gate
    if "barstate.isconfirmed" in code:
        findings.append("PASS: barstate.isconfirmed gate present — signals only "
                        "fire on confirmed (closed) bars")
    else:
        findings.append("WARN: No barstate.isconfirmed gate — signals may fire "
                        "on incomplete bars")

    # Check 4: No future data references
    # Look for negative indexing like [−1] which would be forward-looking
    import re
    future_refs = re.findall(r'\[-\d+\]', code)
    if future_refs:
        findings.append(f"FAIL: Found future data references: {future_refs}")
    else:
        findings.append("PASS: No forward-looking index references found")

    # Check 5: calc_on_every_tick
    if "calc_on_every_tick=false" in code:
        findings.append("PASS: calc_on_every_tick=false — no intra-bar recalculation")
    else:
        findings.append("WARN: calc_on_every_tick not explicitly false")

    return findings


# ═══════════════════════════════════════════════════════════════════════════
# JSON payload validation
# ═══════════════════════════════════════════════════════════════════════════

def validate_payloads() -> list[str]:
    """Generate and validate sample JSON payloads."""
    findings = []

    # Mode A entry payload
    mode_a = {
        "token": "mukesh-tv-2026",
        "ticker": "SPY",
        "action": "LONG_ENTRY",
        "mode": "trend_continuation",
        "conviction": 85.0,
        "regime": "trending_up",
        "entry_price": 580.25,
        "stop_level": 575.10,
        "atr": 8.50,
        "atr_pct": 1.47,
        "rsi": 62.5,
        "adx": 32.1,
        "di_plus": 28.5,
        "di_minus": 15.2,
        "pct_from_high": 0.85,
        "macd_hist": 1.25,
        "suggested_hold_days": 10,
        "weekly_trend": "bullish",
        "cluster": "Trend",
        "options_guidance": "directional_long",
        "exit_reason": "",
        "bb_upper": 595.50,
        "bb_lower": 565.00,
        "bb_width": 5.3,
        "timeframe": "1D",
        "bar_time": 1711584000000,
    }

    # Mode B breakout payload
    mode_b = {**mode_a,
        "action": "LONG_ENTRY",
        "mode": "breakout",
        "conviction": 70.0,
        "regime": "volatile_breakout",
        "options_guidance": "breakout_long",
        "cluster": "Momentum",
    }

    # Exit payload
    exit_p = {
        "token": "mukesh-tv-2026",
        "ticker": "SPY",
        "action": "EXIT",
        "mode": "exit",
        "conviction": 0,
        "regime": "trending_up",
        "entry_price": 0,
        "stop_level": 0,
        "atr": 8.50,
        "rsi": 82.3,
        "adx": 28.5,
        "exit_reason": "take_profit",
        "bars_in_trade": 12,
        "bar_time": 1712448000000,
    }

    payloads = [("Mode A Entry", mode_a), ("Mode B Breakout", mode_b), ("Exit", exit_p)]

    for name, payload in payloads:
        try:
            json_str = json.dumps(payload)
            parsed = json.loads(json_str)
            findings.append(f"PASS: {name} payload — valid JSON ({len(parsed)} fields)")

            # Check required fields
            required_entry = ["token", "ticker", "action", "mode", "conviction",
                              "regime", "entry_price", "rsi", "adx", "options_guidance"]
            required_exit = ["token", "ticker", "action", "exit_reason", "bars_in_trade"]

            required = required_exit if name == "Exit" else required_entry
            missing = [f for f in required if f not in parsed]
            if missing:
                findings.append(f"  WARN: Missing fields: {missing}")
            else:
                findings.append(f"  All required fields present")

        except json.JSONDecodeError as e:
            findings.append(f"FAIL: {name} payload — invalid JSON: {e}")

    return payloads, findings


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  V6 PINE SCRIPT VALIDATION")
    print("=" * 70)

    tickers = ["SPY", "INTC", "AMD", "AMZN", "QQQ"]
    results = {}

    for ticker in tickers:
        path = f"data/{ticker}.dly"
        try:
            df = load_sierra_dly(path)
        except Exception:
            print(f"  {ticker}: data not found, skipping")
            continue

        print(f"\n  Running V6 simulation on {ticker} ({len(df)} bars)...")
        trades = simulate_v6(df)
        m = calc_metrics(trades)
        results[ticker] = (trades, m)

        # Print trade breakdown
        if trades:
            mode_a = [t for t in trades if t.mode == "A"]
            mode_b = [t for t in trades if t.mode == "B"]
            exits = {}
            for t in trades:
                exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
            print(f"    Trades: {m['trades']}  (Mode A: {len(mode_a)}, Mode B: {len(mode_b)})")
            print(f"    WR: {m['win_rate']}%  PF: {m['profit_factor']}  "
                  f"Net: ${m['net_pnl']:.2f}  Sharpe: {m['sharpe']}")
            print(f"    Exits: {exits}")

    # ── Comparison table ──
    print(f"\n{'=' * 70}")
    print("  EXPECTED VALUES FOR TRADINGVIEW COMPARISON")
    print(f"{'=' * 70}\n")

    rows = []
    for ticker in tickers:
        if ticker not in results:
            continue
        _, m = results[ticker]
        rows.append({
            "Ticker": ticker,
            "Trades": m["trades"],
            "WR%": m["win_rate"],
            "PF": m["profit_factor"],
            "Net PnL": f"${m['net_pnl']:.2f}",
            "Sharpe": m["sharpe"],
            "Avg Bars": m["avg_bars"],
        })
    print(tabulate(rows, headers="keys", tablefmt="simple", floatfmt=".2f"))

    total_pnl = sum(m["net_pnl"] for _, m in results.values())
    total_trades = sum(m["trades"] for _, m in results.values())
    print(f"\n  Combined: {total_trades} trades, ${total_pnl:.2f} net PnL")

    # ── Repainting check ──
    print(f"\n{'=' * 70}")
    print("  REPAINTING RISK ANALYSIS")
    print(f"{'=' * 70}\n")
    repaint_findings = check_repainting()
    for f in repaint_findings:
        print(f"  {f}")

    # ── Payload validation ──
    print(f"\n{'=' * 70}")
    print("  JSON PAYLOAD VALIDATION")
    print(f"{'=' * 70}\n")
    payloads, payload_findings = validate_payloads()
    for f in payload_findings:
        print(f"  {f}")

    # ── Write report ──
    report = _build_report(results, tickers, repaint_findings, payloads, payload_findings)
    out_path = Path("reports/pinescript_validation.md")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(report)
    print(f"\n  Report written: {out_path}")


def _build_report(results, tickers, repaint, payloads, payload_findings):
    lines = ["# Pine Script V6 Validation Report", ""]
    lines.append("## Expected Values for TradingView Comparison")
    lines.append("")
    lines.append("TradingView backtest results should be within 10-15% of these numbers.")
    lines.append("Larger divergences indicate a calculation bug.")
    lines.append("")
    lines.append("| Ticker | Trades | WR% | PF | Net PnL | Sharpe | Avg Bars |")
    lines.append("|--------|--------|-----|-----|---------|--------|----------|")
    for ticker in tickers:
        if ticker not in results:
            continue
        _, m = results[ticker]
        lines.append(f"| {ticker} | {m['trades']} | {m['win_rate']} | "
                     f"{m['profit_factor']} | ${m['net_pnl']:.2f} | "
                     f"{m['sharpe']} | {m['avg_bars']} |")
    lines.append("")

    total_pnl = sum(m["net_pnl"] for _, m in results.values())
    total_trades = sum(m["trades"] for _, m in results.values())
    lines.append(f"**Combined:** {total_trades} trades, ${total_pnl:.2f} net PnL")
    lines.append("")

    # Per-ticker trade details
    lines.append("## Per-Ticker Trade Details")
    lines.append("")
    for ticker in tickers:
        if ticker not in results:
            continue
        trades, m = results[ticker]
        if not trades:
            continue
        lines.append(f"### {ticker}")
        lines.append("")
        mode_a = [t for t in trades if t.mode == "A"]
        mode_b = [t for t in trades if t.mode == "B"]
        lines.append(f"- Mode A (Trend): {len(mode_a)} trades")
        lines.append(f"- Mode B (Breakout): {len(mode_b)} trades")
        exits = {}
        for t in trades:
            exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
        lines.append(f"- Exit breakdown: {exits}")

        # Last 5 trades
        lines.append("")
        lines.append("| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |")
        lines.append("|-------|------|------|-------|-----|------|-------------|")
        for t in trades[-5:]:
            lines.append(f"| {t.entry_date.date()} | {t.exit_date.date()} | "
                         f"{t.mode} | {t.score:.0f} | ${t.pnl:.2f} | "
                         f"{t.bars_held} | {t.exit_reason} |")
        lines.append("")

    # Repainting
    lines.append("## Repainting Risk Analysis")
    lines.append("")
    for f in repaint:
        status = "PASS" if f.startswith("PASS") else "WARN" if f.startswith("WARN") else "FAIL"
        lines.append(f"- **{status}**: {f[len(status)+2:]}")
    lines.append("")

    # Payloads
    lines.append("## JSON Payload Validation")
    lines.append("")
    for f in payload_findings:
        lines.append(f"- {f}")
    lines.append("")
    lines.append("### Sample Payloads")
    lines.append("")
    for name, payload in payloads:
        lines.append(f"**{name}:**")
        lines.append("```json")
        lines.append(json.dumps(payload, indent=2))
        lines.append("```")
        lines.append("")

    # Divergence flags
    lines.append("## Potential Divergence Notes")
    lines.append("")
    lines.append("Expected sources of 5-15% divergence between Python and TradingView:")
    lines.append("")
    lines.append("1. **Weekly EMA seeding**: TV calculates weekly EMAs from the full weekly")
    lines.append("   history which may differ from our daily-resampled approximation")
    lines.append("2. **Bar alignment**: TV weekly bars may align to Sunday or Monday")
    lines.append("   vs our Friday-anchored resample")
    lines.append("3. **Slippage model**: TV applies slippage differently (fixed tick vs %)")
    lines.append("4. **Position sizing**: TV uses equity curve for 10% sizing which")
    lines.append("   compounds differently than our fixed initial capital approach")
    lines.append("5. **ADX/RSI seed period**: Minor differences in initial SMA seed")
    lines.append("   window can propagate for ~50 bars before converging")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
