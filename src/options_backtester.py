#!/usr/bin/env python3
"""
Options-specific swing trade backtester.

Models 3 outcomes: WIN (+50% premium), FLAT_LOSS (theta decay), LOSS (full premium).
Designed for 45-60 DTE options with 21 DTE mandatory exit (≈20 trading bars max hold).

Usage: python src/options_backtester.py
"""

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_sierra_dly
from indicator_research import compute_indicators
from indicators import calc_ema, calc_sma

TICKERS = ["SPY", "QQQ", "IWM", "SLV", "GLD", "XLE", "XLF",
           "NVDA", "TSLA", "AMD", "MSFT", "META", "AMZN", "SOFI", "INTC"]
DATA_START = "2020-01-01"

# Cluster assignments from Step 1
CLUSTERS = {
    "trend_pullback": ["GLD", "NVDA", "TSLA", "AMD", "MSFT", "INTC"],
    "momentum_breakout": ["SLV", "XLE", "AMZN", "SOFI"],
    "mean_reversion": ["SPY", "QQQ", "IWM", "XLF", "META"],
}
TICKER_ARCHETYPE = {}
for arch, tickers in CLUSTERS.items():
    for t in tickers:
        TICKER_ARCHETYPE[t] = arch

# Default parameters
DEFAULTS = {
    "max_hold_bars": 20,
    "atr_stop_mult": 2.0,
    "atr_target_mult": 2.0,
    "cooldown_pullback_pct": 0.02,
    "risk_budget": 500.0,
    "premium_atr_ratio": 0.30,
    "slippage": 0.01,
}


# ═══════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class OptionsTrade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    direction: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    outcome: str          # "WIN", "FLAT_LOSS", "LOSS"
    pnl: float
    bars_held: int
    strategy: str
    signal: str
    contracts: int


@dataclass
class OptionsTradeLog:
    trades: list[OptionsTrade] = field(default_factory=list)

    def to_dataframe(self):
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([{
            "Entry": t.entry_date, "Exit": t.exit_date, "Dir": t.direction,
            "Entry$": round(t.entry_price, 2), "Exit$": round(t.exit_price, 2),
            "Stop": round(t.stop_price, 2), "Target": round(t.target_price, 2),
            "Outcome": t.outcome, "PnL": round(t.pnl, 2), "Bars": t.bars_held,
            "Strategy": t.strategy, "Signal": t.signal, "Contracts": t.contracts,
        } for t in self.trades])

    def summary(self):
        if not self.trades:
            return {"total": 0}
        n = len(self.trades)
        wins = [t for t in self.trades if t.outcome == "WIN"]
        flats = [t for t in self.trades if t.outcome == "FLAT_LOSS"]
        losses = [t for t in self.trades if t.outcome == "LOSS"]

        gp = sum(t.pnl for t in wins)
        gl = abs(sum(t.pnl for t in flats)) + abs(sum(t.pnl for t in losses))

        avg_bars_w = np.mean([t.bars_held for t in wins]) if wins else 0
        avg_bars_l = np.mean([t.bars_held for t in losses]) if losses else 0

        # Max consecutive losses
        max_consec = 0
        consec = 0
        for t in self.trades:
            if t.outcome != "WIN":
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0

        return {
            "total": n,
            "wins": len(wins), "flat_losses": len(flats), "losses": len(losses),
            "win_rate": round(100 * len(wins) / n, 1),
            "flat_rate": round(100 * len(flats) / n, 1),
            "loss_rate": round(100 * len(losses) / n, 1),
            "net_pnl": round(sum(t.pnl for t in self.trades), 2),
            "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
            "expectancy": round(sum(t.pnl for t in self.trades) / n, 2),
            "avg_bars_winners": round(avg_bars_w, 1),
            "avg_bars_losers": round(avg_bars_l, 1),
            "max_consec_losses": max_consec,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Signal generators per archetype
# ═══════════════════════════════════════════════════════════════════════════

def gen_trend_pullback_signals(df, ind):
    """Trend Pullback: EMA21 bounce + confirmations."""
    close = df["Close"]
    ema9 = ind["ema9"]
    ema21 = ind["ema21"]
    rsi = ind["rsi14"]
    hist = ind["histogram"]

    # Long: price touched EMA21 within 5 bars, now closing above, trend intact
    touched = (df["Low"].shift(1) <= ema21.shift(1)) | (df["Low"].shift(2) <= ema21.shift(2)) | \
              (df["Low"].shift(3) <= ema21.shift(3)) | (df["Low"].shift(4) <= ema21.shift(4))
    long_sig = touched & (close > ema21) & (ema9 > ema21) & (rsi > 50) & (hist > 0)

    # Short: mirror (only for INTC which has proven short signals)
    touched_hi = (df["High"].shift(1) >= ema21.shift(1)) | (df["High"].shift(2) >= ema21.shift(2)) | \
                 (df["High"].shift(3) <= ema21.shift(3)) | (df["High"].shift(4) >= ema21.shift(4))
    short_sig = touched_hi & (close < ema21) & (ema9 < ema21) & (rsi < 50) & (hist < 0)

    return long_sig.fillna(False), short_sig.fillna(False), "ema21_pullback"


def gen_momentum_breakout_signals(df, ind):
    """Momentum Breakout: Donchian/Keltner break + volume."""
    close = df["Close"]
    vol = df["Volume"]
    vol_sma = ind["vol_sma20"]
    donch_hi = ind["donchian_high"]
    donch_lo = ind["donchian_low"]
    kelt_upper = ind["kelt_upper"]
    kelt_lower = ind["kelt_lower"]

    vol_spike = vol > vol_sma * 1.5

    long_sig = ((close > donch_hi.shift(1)) | (close > kelt_upper.shift(1))) & vol_spike
    short_sig = ((close < donch_lo.shift(1)) | (close < kelt_lower.shift(1))) & vol_spike

    return long_sig.fillna(False), short_sig.fillna(False), "breakout"


def gen_mean_reversion_signals(df, ind):
    """Mean Reversion: BB touch bounce + MACD flip."""
    close = df["Close"]
    bb_lower = ind["bb_lower"]
    bb_upper = ind["bb_upper"]
    bb_mid = ind["bb_mid"]
    hist = ind["histogram"]
    stoch_k = ind["stoch_k"]
    stoch_d = ind["stoch_d"]

    # Long: BB lower touch bounce OR MACD hist flip positive
    bb_bounce = (close.shift(1) <= bb_lower.shift(1)) & (close > bb_lower)
    macd_flip = (hist > 0) & (hist.shift(1) <= 0)
    stoch_up = (stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1)) & (stoch_k < 30)

    long_sig = (bb_bounce | macd_flip) & ((stoch_k < 50) | (close < bb_mid))

    # Short: BB upper touch + MACD flip negative
    bb_reject = (close.shift(1) >= bb_upper.shift(1)) & (close < bb_upper)
    macd_flip_dn = (hist < 0) & (hist.shift(1) >= 0)
    short_sig = (bb_reject | macd_flip_dn) & ((stoch_k > 50) | (close > bb_mid))

    return long_sig.fillna(False), short_sig.fillna(False), "mean_rev"


ARCHETYPE_SIGNALS = {
    "trend_pullback": gen_trend_pullback_signals,
    "momentum_breakout": gen_momentum_breakout_signals,
    "mean_reversion": gen_mean_reversion_signals,
}


# ═══════════════════════════════════════════════════════════════════════════
# Options Backtester
# ═══════════════════════════════════════════════════════════════════════════

class OptionsBacktester:
    def __init__(self, ticker: str, archetype: str, params: dict = None):
        self.ticker = ticker
        self.archetype = archetype
        self.p = {**DEFAULTS, **(params or {})}

    def run(self, df: pd.DataFrame) -> OptionsTradeLog:
        p = self.p
        n = len(df)
        if n < 300:
            return OptionsTradeLog()

        ind = compute_indicators(df)
        close = df["Close"]
        atr = ind["atr"]
        swing_hi = ind["swing_hi"]
        swing_lo = ind["swing_lo"]
        dates = df.index

        # Generate signals
        sig_func = ARCHETYPE_SIGNALS[self.archetype]
        long_sig, short_sig, sig_name = sig_func(df, ind)

        # Slice to focus window
        focus_start = pd.Timestamp(DATA_START)
        focus_mask = np.array(dates >= focus_start)

        trades = []
        in_trade = False
        pending = False
        pend_dir = ""
        pend_bar = 0
        entry_bar = 0
        entry_price = 0.0
        stop_price = 0.0
        target_price = 0.0
        last_sig_close = 0.0
        swing_active = False
        last_exit_bar = -10
        contracts = 1

        for i in range(1, n):
            if not focus_mask[i]:
                continue
            c = close.iat[i]
            if np.isnan(atr.iat[i]) or atr.iat[i] <= 0:
                continue

            # Enter pending
            if pending and not in_trade and i == pend_bar + 1:
                entry_price = df["Open"].iat[i] + p["slippage"]
                a = atr.iat[i]
                premium = a * p["premium_atr_ratio"]
                contracts = max(1, int(p["risk_budget"] / max(premium, 0.01)))

                if pend_dir == "long":
                    sw_stop = swing_lo.iat[i] if not np.isnan(swing_lo.iat[i]) else entry_price - 2 * a
                    stop_price = max(sw_stop, entry_price - p["atr_stop_mult"] * a)
                    target_price = entry_price + p["atr_target_mult"] * a
                else:
                    sw_stop = swing_hi.iat[i] if not np.isnan(swing_hi.iat[i]) else entry_price + 2 * a
                    stop_price = min(sw_stop, entry_price + p["atr_stop_mult"] * a)
                    target_price = entry_price - p["atr_target_mult"] * a

                in_trade = True
                entry_bar = i
                last_sig_close = c
                swing_active = True
                pending = False

            # Manage trade
            if in_trade:
                bars_held = i - entry_bar
                bar_high = df["High"].iat[i]
                bar_low = df["Low"].iat[i]

                if pend_dir == "long":
                    sl_hit = bar_low <= stop_price
                    tp_hit = bar_high >= target_price
                else:
                    sl_hit = bar_high >= stop_price
                    tp_hit = bar_low <= target_price

                outcome = None
                exit_price = c

                if sl_hit and tp_hit:
                    outcome = "LOSS"
                    exit_price = stop_price
                elif sl_hit:
                    outcome = "LOSS"
                    exit_price = stop_price
                elif tp_hit:
                    outcome = "WIN"
                    exit_price = target_price
                elif bars_held >= p["max_hold_bars"]:
                    outcome = "FLAT_LOSS"
                    exit_price = c

                if outcome:
                    premium = atr.iat[entry_bar] * p["premium_atr_ratio"]
                    if outcome == "WIN":
                        trade_pnl = premium * 0.5 * contracts
                    elif outcome == "FLAT_LOSS":
                        trade_pnl = -premium * 0.5 * contracts
                    else:
                        trade_pnl = -premium * contracts

                    trades.append(OptionsTrade(
                        entry_date=dates[entry_bar], exit_date=dates[i],
                        direction=pend_dir, entry_price=entry_price,
                        exit_price=exit_price, stop_price=stop_price,
                        target_price=target_price, outcome=outcome,
                        pnl=round(trade_pnl, 2), bars_held=bars_held,
                        strategy=self.archetype, signal=sig_name,
                        contracts=contracts,
                    ))
                    in_trade = False
                    swing_active = False
                    last_exit_bar = i
                    continue

            if in_trade:
                continue

            # Cooldown: 5 bars minimum + swing pullback
            if i - last_exit_bar < 5:
                continue

            # Swing cooldown: require 2% pullback between same-direction signals
            if swing_active and last_sig_close > 0:
                pullback = abs(c - last_sig_close) / last_sig_close
                if pullback < p["cooldown_pullback_pct"]:
                    continue
                swing_active = False

            # Check signals
            if long_sig.iat[i]:
                pending = True
                pend_dir = "long"
                pend_bar = i
            elif short_sig.iat[i]:
                pending = True
                pend_dir = "short"
                pend_bar = i

        return OptionsTradeLog(trades=trades)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  OPTIONS SWING TRADE BACKTESTER")
    print("=" * 70)

    results = []
    all_trades = []

    for ticker in TICKERS:
        try:
            df = load_sierra_dly(f"data/{ticker}.dly")
        except Exception:
            print(f"  {ticker}: data not found")
            continue

        archetype = TICKER_ARCHETYPE.get(ticker, "mean_reversion")
        bt = OptionsBacktester(ticker, archetype)
        log = bt.run(df)
        s = log.summary()

        if s["total"] == 0:
            results.append({"Ticker": ticker, "Arch": archetype[:8], "Trades": 0,
                            "WR%": 0, "Flat%": 0, "Loss%": 0, "PF": 0,
                            "Net$": 0, "Expect$": 0, "AvgBarsW": 0, "MaxCL": 0})
            continue

        years = (df[df.index >= pd.Timestamp(DATA_START)].index[-1] -
                 pd.Timestamp(DATA_START)).days / 365.25
        sig_mo = s["total"] / (years * 12) if years > 0 else 0

        results.append({
            "Ticker": ticker, "Arch": archetype[:8],
            "Trades": s["total"], "WR%": s["win_rate"],
            "Flat%": s["flat_rate"], "Loss%": s["loss_rate"],
            "PF": s["profit_factor"], "Net$": s["net_pnl"],
            "Expect$": s["expectancy"],
            "AvgBarsW": s["avg_bars_winners"], "MaxCL": s["max_consec_losses"],
            "Sig/Mo": round(sig_mo, 1),
        })

        all_trades.extend(log.trades)

        # Per-signal breakdown for this ticker
        tdf = log.to_dataframe()
        if len(tdf) > 0:
            long_t = tdf[tdf["Dir"] == "long"]
            short_t = tdf[tdf["Dir"] == "short"]
            long_wr = 100 * (long_t["Outcome"] == "WIN").mean() if len(long_t) > 0 else 0
            short_wr = 100 * (short_t["Outcome"] == "WIN").mean() if len(short_t) > 0 else 0
            print(f"  {ticker:>6s} [{archetype[:8]:>8s}]: {s['total']:>3d} trades  "
                  f"WR={s['win_rate']:>5.1f}%  Flat={s['flat_rate']:>5.1f}%  "
                  f"PF={s['profit_factor']:>5.2f}  ${s['net_pnl']:>8.0f}  "
                  f"L:{len(long_t)}({long_wr:.0f}%) S:{len(short_t)}({short_wr:.0f}%)")

    print(f"\n{'=' * 70}")
    print(tabulate(results, headers="keys", tablefmt="simple", floatfmt=".1f"))

    # Aggregate
    if all_trades:
        total = len(all_trades)
        total_pnl = sum(t.pnl for t in all_trades)
        total_wins = sum(1 for t in all_trades if t.outcome == "WIN")
        total_flats = sum(1 for t in all_trades if t.outcome == "FLAT_LOSS")
        total_losses = sum(1 for t in all_trades if t.outcome == "LOSS")
        print(f"\n  Portfolio: {total} trades, ${total_pnl:,.0f} net")
        print(f"  Outcomes: {total_wins} wins ({100*total_wins/total:.1f}%), "
              f"{total_flats} flat ({100*total_flats/total:.1f}%), "
              f"{total_losses} losses ({100*total_losses/total:.1f}%)")

    # Direction qualification
    print(f"\n  DIRECTION QUALIFICATION (OOS WR>45%, PF>1.3):")
    for r in results:
        if r["Trades"] == 0:
            print(f"    {r['Ticker']:>6s}: EXCLUDED (no trades)")
            continue
        qualified = r["WR%"] > 45 and r["PF"] > 1.3
        print(f"    {r['Ticker']:>6s}: {'QUALIFIED' if qualified else 'MARGINAL'} "
              f"(WR={r['WR%']:.1f}%, PF={r['PF']:.2f})")


if __name__ == "__main__":
    main()
