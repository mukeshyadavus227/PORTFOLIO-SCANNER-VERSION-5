"""
Four sub-strategy signal generators for Portfolio Scanner V5.

Each strategy generates independent long/short signals with a conviction
strength score (0-1).  Signals are only emitted during the strategy's
active regime(s).
"""

from abc import ABC, abstractmethod
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicators import (
    calc_adx,
    calc_atr,
    calc_bollinger,
    calc_choppiness_index,
    calc_ema,
    calc_macd,
    calc_range_filter,
    calc_rsi,
    calc_sma,
    calc_stochastic,
    calc_supertrend,
    calc_vwap,
    calc_waddah_attar,
)
from regime import detect_regime


# ═══════════════════════════════════════════════════════════════════════════
# Shared indicator cache
# ═══════════════════════════════════════════════════════════════════════════

def compute_all_indicators(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Pre-compute every indicator needed by all four strategies."""
    close = df["Close"]
    has_volume = "Volume" in df.columns and (df["Volume"] > 0).any()

    plus_di, minus_di, adx = calc_adx(df, 14, 14)
    atr = calc_atr(df, 14)
    macd_line, signal_line, histogram = calc_macd(close, 12, 26, 9)
    bb_upper, bb_mid, bb_lower = calc_bollinger(close, 20, 2.0)
    stoch_k, stoch_d = calc_stochastic(df, 14, 3, 3)
    wae_expl, wae_dead, wae_dir = calc_waddah_attar(df)
    st_dir, st_val = calc_supertrend(df, 10, 3.0)

    vol_sma20 = calc_sma(df["Volume"], 20) if has_volume else pd.Series(0.0, index=df.index)

    ind = {
        # Trend
        "ema9": calc_ema(close, 9),
        "ema21": calc_ema(close, 21),
        "ema50": calc_ema(close, 50),
        "ema200": calc_ema(close, 200),
        "sma200": calc_sma(close, 200),
        # Momentum
        "rsi14": calc_rsi(close, 14),
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "chop": calc_choppiness_index(df, 14),
        # Volatility
        "atr": atr,
        "atr_sma20": calc_sma(atr, 20),
        # MACD
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
        # Bollinger
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
        # Stochastic
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        # VWAP
        "vwap": calc_vwap(df),
        # SuperTrend
        "st_dir": st_dir,
        "st_val": st_val,
        # Range Filter
        "range_filter": calc_range_filter(close, 100, 3.0),
        # WAE
        "wae_expl": wae_expl,
        "wae_dead": wae_dead,
        "wae_dir": wae_dir,
        # Volume
        "vol_sma20": vol_sma20,
        "vol_above_avg": df["Volume"] > vol_sma20 * 1.15 if has_volume else pd.Series(False, index=df.index),
        "vol_spike": df["Volume"] > vol_sma20 * 1.5 if has_volume else pd.Series(False, index=df.index),
        # Donchian
        "donchian_high": df["High"].rolling(20).max(),
        "donchian_low": df["Low"].rolling(20).min(),
        # Swing levels
        "lowest_20": df["Low"].rolling(20).min(),
        "highest_20": df["High"].rolling(20).max(),
    }
    return ind


# ═══════════════════════════════════════════════════════════════════════════
# Base class
# ═══════════════════════════════════════════════════════════════════════════

class Strategy(ABC):
    """Base class for sub-strategies."""

    name: str = "base"
    active_regimes: list[str] = []

    @abstractmethod
    def _score(self, df: pd.DataFrame, ind: dict[str, pd.Series],
               ) -> tuple[pd.Series, pd.Series]:
        """Return (long_score, short_score) as raw 0-100 series."""

    def generate_signals(self, df: pd.DataFrame,
                         ind: dict[str, pd.Series],
                         regime: pd.Series) -> pd.DataFrame:
        """Generate signals gated by active regime.

        Returns DataFrame with columns:
            long_signal  (bool)
            short_signal (bool)
            signal_strength (float 0-1)
        """
        long_score, short_score = self._score(df, ind)

        # Gate by regime
        active = regime.isin(self.active_regimes)
        long_score = long_score.where(active, 0.0)
        short_score = short_score.where(active, 0.0)

        # Threshold: score > 0 means signal fires
        long_signal = long_score > 0
        short_signal = short_score > 0

        # Strength: normalize to 0-1 (cap at 100)
        strength = pd.concat([long_score, short_score], axis=1).max(axis=1).clip(0, 100) / 100.0

        return pd.DataFrame({
            "long_signal": long_signal,
            "short_signal": short_signal,
            "signal_strength": strength,
        }, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
# S1: Trend Following (RSI Mean Reversion in Pine Script V5)
# ═══════════════════════════════════════════════════════════════════════════

class S1_TrendFollowing(Strategy):
    """Trend following using Range Filter direction + ADX/DI confirmation.

    Active in: trending_up, trending_down
    Maps to Pine V5's S1 (RSI Mean-Reversion scoring adapted for trend context).
    """

    name = "S1_TrendFollowing"
    active_regimes = ["trending_up", "trending_down"]

    def _score(self, df: pd.DataFrame, ind: dict[str, pd.Series],
               ) -> tuple[pd.Series, pd.Series]:
        close = df["Close"]
        rsi = ind["rsi14"]
        adx = ind["adx"]
        plus_di = ind["plus_di"]
        minus_di = ind["minus_di"]
        ema200 = ind["ema200"]
        rf = ind["range_filter"]
        atr = ind["atr"]
        vol_ok = ind["vol_above_avg"]

        # Range Filter direction: bullish when price > filter
        rf_bull = (close > rf).fillna(False)
        rf_bear = (close < rf).fillna(False)

        # TRIGGER: Range Filter *turns* bullish/bearish (direction change)
        rf_turns_bull = rf_bull & (~rf_bull.shift(1, fill_value=False))
        rf_turns_bear = rf_bear & (~rf_bear.shift(1, fill_value=False))

        # Allow signal for N bars after the trigger (capture the move)
        lookback = 5
        rf_recent_bull = rf_turns_bull.rolling(lookback, min_periods=1).max().fillna(0).astype(bool) & rf_bull
        rf_recent_bear = rf_turns_bear.rolling(lookback, min_periods=1).max().fillna(0).astype(bool) & rf_bear

        # DI spread as strength multiplier
        di_spread = (plus_di - minus_di).abs()

        # ── Long ──
        # Range Filter turns bullish + price > EMA(200) + ADX > 25 + RSI > 40
        long_base = rf_recent_bull & (close > ema200) & (adx > 25) & (rsi > 40)

        # Graduated scoring (mirrors V5 approach)
        long_score = np.where(long_base & rf_turns_bull, 30.0,
                    np.where(long_base, 20.0, 0.0))                         # fresh trigger vs recent
        long_score += np.where(long_base & (plus_di > minus_di), 20.0, 0.0) # DI confirmation
        long_score += np.where(long_base & (adx > 35), 10.0,
                     np.where(long_base, 5.0, 0.0))                         # strong vs moderate trend
        long_score += np.where(long_base & vol_ok, 15.0, 0.0)              # volume
        long_score += np.where(long_base & (di_spread > 15), 10.0, 0.0)    # wide DI spread
        long_score += np.where(long_base & (rsi > 50) & (rsi < 70), 10.0, 0.0)  # healthy RSI
        long_score = pd.Series(long_score, index=df.index)

        # ── Short ──
        short_base = rf_recent_bear & (close < ema200) & (adx > 25) & (rsi < 60)
        short_score = np.where(short_base & rf_turns_bear, 30.0,
                     np.where(short_base, 20.0, 0.0))
        short_score += np.where(short_base & (minus_di > plus_di), 20.0, 0.0)
        short_score += np.where(short_base & (adx > 35), 10.0,
                      np.where(short_base, 5.0, 0.0))
        short_score += np.where(short_base & vol_ok, 15.0, 0.0)
        short_score += np.where(short_base & (di_spread > 15), 10.0, 0.0)
        short_score += np.where(short_base & (rsi < 50) & (rsi > 30), 10.0, 0.0)
        short_score = pd.Series(short_score, index=df.index)

        return long_score, short_score


# ═══════════════════════════════════════════════════════════════════════════
# S2: Mean Reversion
# ═══════════════════════════════════════════════════════════════════════════

class S2_MeanReversion(Strategy):
    """Mean reversion using RSI extremes + Stochastic + Bollinger Bands.

    Active in: ranging
    """

    name = "S2_MeanReversion"
    active_regimes = ["ranging"]

    def _score(self, df: pd.DataFrame, ind: dict[str, pd.Series],
               ) -> tuple[pd.Series, pd.Series]:
        close = df["Close"]
        rsi = ind["rsi14"]
        stoch_k = ind["stoch_k"]
        stoch_d = ind["stoch_d"]
        bb_upper = ind["bb_upper"]
        bb_mid = ind["bb_mid"]
        bb_lower = ind["bb_lower"]
        chop = ind["chop"]
        atr = ind["atr"]
        vol_ok = ind["vol_above_avg"]

        # Stochastic crossovers
        k_cross_up = (stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1))
        k_cross_down = (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1))

        # Distance from BB bands (normalized by BB width)
        bb_width = (bb_upper - bb_lower).replace(0, np.nan)
        dist_to_lower = (close - bb_lower) / bb_width
        dist_to_upper = (bb_upper - close) / bb_width

        # ── Long ──
        # RSI < 30 + Stoch K crosses up from below 20 + near lower BB + Chop > 61.8
        long_rsi = rsi < 30
        long_stoch = k_cross_up & (stoch_k.shift(1) < 20)
        long_bb = dist_to_lower < 0.2   # within 20% of lower band
        long_chop = chop > 61.8

        # Graduated scoring
        long_score = np.where(long_rsi, 25.0, np.where(rsi < 35, 15.0, 0.0))
        long_score += np.where(long_stoch, 25.0, np.where(k_cross_up, 10.0, 0.0))
        long_score += np.where(long_bb, 20.0, np.where(dist_to_lower < 0.35, 10.0, 0.0))
        long_score += np.where(long_chop, 15.0, 0.0)
        long_score += np.where(vol_ok, 10.0, 0.0)
        long_score = pd.Series(long_score, index=df.index)

        # Require at least RSI oversold OR Stoch cross for signal to fire
        long_gate = long_rsi | long_stoch
        long_score = long_score.where(long_gate, 0.0)

        # ── Short ──
        short_rsi = rsi > 70
        short_stoch = k_cross_down & (stoch_k.shift(1) > 80)
        short_bb = dist_to_upper < 0.2
        short_chop = chop > 61.8

        short_score = np.where(short_rsi, 25.0, np.where(rsi > 65, 15.0, 0.0))
        short_score += np.where(short_stoch, 25.0, np.where(k_cross_down, 10.0, 0.0))
        short_score += np.where(short_bb, 20.0, np.where(dist_to_upper < 0.35, 10.0, 0.0))
        short_score += np.where(short_chop, 15.0, 0.0)
        short_score += np.where(vol_ok, 10.0, 0.0)
        short_score = pd.Series(short_score, index=df.index)

        short_gate = short_rsi | short_stoch
        short_score = short_score.where(short_gate, 0.0)

        return long_score, short_score


# ═══════════════════════════════════════════════════════════════════════════
# S3: Breakout Momentum (Donchian Breakout in Pine Script V5)
# ═══════════════════════════════════════════════════════════════════════════

class S3_BreakoutMomentum(Strategy):
    """Breakout momentum using Donchian channels + Volume + MACD + WAE.

    Active in: volatile (transitioning from range to trend)
    Maps to Pine V5's S2 (Donchian Breakout).
    """

    name = "S3_BreakoutMomentum"
    active_regimes = ["volatile"]

    def _score(self, df: pd.DataFrame, ind: dict[str, pd.Series],
               ) -> tuple[pd.Series, pd.Series]:
        close = df["Close"]
        atr = ind["atr"]
        adx = ind["adx"]
        histogram = ind["histogram"]
        vol_spike = ind["vol_spike"]
        vol_ok = ind["vol_above_avg"]
        wae_expl = ind["wae_expl"]
        wae_dead = ind["wae_dead"]
        wae_dir = ind["wae_dir"]
        sma50 = calc_sma(close, 50)
        atr_expanding = atr > ind["atr_sma20"] * 1.2

        donchian_high_prev = ind["donchian_high"].shift(1)
        donchian_low_prev = ind["donchian_low"].shift(1)

        # Volume gate: must have at least above-average volume
        has_volume = vol_spike | vol_ok

        # Extension filter: block if already stretched 1.5 ATR beyond 50-SMA
        extended_up = close > sma50 + atr * 1.5
        extended_down = close < sma50 - atr * 1.5

        # MACD histogram turning positive/negative
        hist_turning_pos = (histogram > 0) & (histogram.shift(1) <= 0)
        hist_positive = histogram > 0
        hist_turning_neg = (histogram < 0) & (histogram.shift(1) >= 0)
        hist_negative = histogram < 0

        # WAE explosion > dead zone
        wae_active = wae_expl > wae_dead

        # ── Long ──
        break_high = close > donchian_high_prev
        long_gate = break_high & has_volume & ~extended_up

        long_score = np.where(long_gate, 30.0, 0.0)                           # breakout confirmed
        long_score += np.where(long_gate & (close > sma50), 15.0, 0.0)        # above trend
        long_score += np.where(long_gate & (adx > 25), 15.0,
                      np.where(long_gate & (adx > 20), 8.0, 0.0))             # ADX strength
        long_score += np.where(long_gate & vol_spike, 20.0,
                      np.where(long_gate & vol_ok, 10.0, 0.0))                # volume magnitude
        long_score += np.where(long_gate & (hist_turning_pos | hist_positive), 10.0, 0.0)
        long_score += np.where(long_gate & wae_active & (wae_dir > 0), 10.0, 0.0)
        long_score = pd.Series(long_score, index=df.index)

        # ── Short ──
        break_low = close < donchian_low_prev
        short_gate = break_low & has_volume & ~extended_down

        short_score = np.where(short_gate, 30.0, 0.0)
        short_score += np.where(short_gate & (close < sma50), 15.0, 0.0)
        short_score += np.where(short_gate & (adx > 25), 15.0,
                       np.where(short_gate & (adx > 20), 8.0, 0.0))
        short_score += np.where(short_gate & vol_spike, 20.0,
                       np.where(short_gate & vol_ok, 10.0, 0.0))
        short_score += np.where(short_gate & (hist_turning_neg | hist_negative), 10.0, 0.0)
        short_score += np.where(short_gate & wae_active & (wae_dir < 0), 10.0, 0.0)
        short_score = pd.Series(short_score, index=df.index)

        return long_score, short_score


# ═══════════════════════════════════════════════════════════════════════════
# S4: Range Scalp
# ═══════════════════════════════════════════════════════════════════════════

class S4_RangeScalp(Strategy):
    """Range scalp using SuperTrend + Stochastic + VWAP bounces.

    Active in: ranging (tight range, low ADX)
    """

    name = "S4_RangeScalp"
    active_regimes = ["ranging"]

    def _score(self, df: pd.DataFrame, ind: dict[str, pd.Series],
               ) -> tuple[pd.Series, pd.Series]:
        close = df["Close"]
        st_dir = ind["st_dir"]
        stoch_k = ind["stoch_k"]
        stoch_d = ind["stoch_d"]
        vwap = ind["vwap"]
        bb_upper = ind["bb_upper"]
        bb_lower = ind["bb_lower"]
        bb_mid = ind["bb_mid"]
        adx = ind["adx"]

        # SuperTrend flips
        st_flip_bull = (st_dir == 1) & (st_dir.shift(1) == -1)
        st_bull = st_dir == 1
        st_flip_bear = (st_dir == -1) & (st_dir.shift(1) == 1)
        st_bear = st_dir == -1

        # Stochastic oversold/overbought crossovers
        k_cross_up = (stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1))
        k_cross_down = (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1))
        stoch_oversold = stoch_k < 20
        stoch_overbought = stoch_k > 80

        # VWAP bounces
        vwap_bounce_up = (close > vwap) & (close.shift(1) <= vwap.shift(1))
        vwap_bounce_down = (close < vwap) & (close.shift(1) >= vwap.shift(1))

        # Range boundary proximity (how close to BB edges)
        bb_width = (bb_upper - bb_lower).replace(0, np.nan)
        near_lower = (close - bb_lower) / bb_width < 0.25
        near_upper = (bb_upper - close) / bb_width < 0.25

        # ── Long ──
        # SuperTrend flip/bull + Stochastic oversold cross + VWAP bounce from below
        long_st = st_flip_bull | (st_bull & k_cross_up)
        long_stoch = k_cross_up & (stoch_oversold | (stoch_k.shift(1) < 30))
        long_vwap = vwap_bounce_up

        long_gate = long_st | (long_stoch & long_vwap)

        long_score = np.where(long_gate & st_flip_bull, 25.0,
                    np.where(long_gate & st_bull, 15.0, 10.0))
        long_score += np.where(long_gate & long_stoch, 25.0,
                     np.where(long_gate & k_cross_up, 10.0, 0.0))
        long_score += np.where(long_gate & long_vwap, 20.0, 0.0)
        long_score += np.where(long_gate & near_lower, 15.0, 0.0)      # near range bottom
        long_score += np.where(long_gate & (adx < 15), 10.0, 0.0)      # very tight range
        long_score = pd.Series(long_score, index=df.index)
        long_score = long_score.where(long_gate, 0.0)

        # ── Short ──
        short_st = st_flip_bear | (st_bear & k_cross_down)
        short_stoch = k_cross_down & (stoch_overbought | (stoch_k.shift(1) > 70))
        short_vwap = vwap_bounce_down

        short_gate = short_st | (short_stoch & short_vwap)

        short_score = np.where(short_gate & st_flip_bear, 25.0,
                     np.where(short_gate & st_bear, 15.0, 10.0))
        short_score += np.where(short_gate & short_stoch, 25.0,
                      np.where(short_gate & k_cross_down, 10.0, 0.0))
        short_score += np.where(short_gate & short_vwap, 20.0, 0.0)
        short_score += np.where(short_gate & near_upper, 15.0, 0.0)
        short_score += np.where(short_gate & (adx < 15), 10.0, 0.0)
        short_score = pd.Series(short_score, index=df.index)
        short_score = short_score.where(short_gate, 0.0)

        return long_score, short_score


# ═══════════════════════════════════════════════════════════════════════════
# All strategies
# ═══════════════════════════════════════════════════════════════════════════

ALL_STRATEGIES = [
    S1_TrendFollowing(),
    S2_MeanReversion(),
    S3_BreakoutMomentum(),
    S4_RangeScalp(),
]


# ═══════════════════════════════════════════════════════════════════════════
# CLI test harness
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data_loader import load_sierra_dly

    df = load_sierra_dly("data/SPY.dly")
    print(f"SPY: {len(df)} rows, {df.index.min().date()} → {df.index.max().date()}\n")

    # Compute indicators and regime once
    ind = compute_all_indicators(df)
    regime = detect_regime(df, {
        "adx": ind["adx"],
        "plus_di": ind["plus_di"],
        "minus_di": ind["minus_di"],
        "atr": ind["atr"],
        "atr_sma20": ind["atr_sma20"],
        "chop": ind["chop"],
        "ema200": ind["ema200"],
    })

    # Regime distribution for context
    regime_counts = regime.value_counts()
    print("Regime distribution:")
    for r in ["trending_up", "trending_down", "ranging", "volatile", "undefined"]:
        n = regime_counts.get(r, 0)
        print(f"  {r:>16s}: {n:>5d}  ({100*n/len(regime):5.1f}%)")
    print()

    # Run each strategy
    summary_rows = []
    for strat in ALL_STRATEGIES:
        signals = strat.generate_signals(df, ind, regime)

        n_long = signals["long_signal"].sum()
        n_short = signals["short_signal"].sum()
        n_total = n_long + n_short
        pct = 100 * n_total / len(df)

        # Which regime triggered most signals
        active_bars = signals["long_signal"] | signals["short_signal"]
        if active_bars.any():
            regime_at_signal = regime[active_bars]
            top_regime = regime_at_signal.value_counts().idxmax()
            avg_strength = signals.loc[active_bars, "signal_strength"].mean()
        else:
            top_regime = "n/a"
            avg_strength = 0.0

        summary_rows.append({
            "Strategy": strat.name,
            "Long": int(n_long),
            "Short": int(n_short),
            "Total": int(n_total),
            "% Bars": round(pct, 2),
            "Avg Strength": round(avg_strength, 3),
            "Top Regime": top_regime,
            "Active In": ", ".join(strat.active_regimes),
        })

        # Show last few signals
        recent = signals[active_bars].tail(5)
        if len(recent):
            print(f"--- {strat.name}: last 5 signals ---")
            for dt, row in recent.iterrows():
                direction = "LONG" if row["long_signal"] else "SHORT"
                print(f"  {dt.date()}  {direction:>5s}  strength={row['signal_strength']:.2f}  regime={regime[dt]}")
            print()

    print("=" * 85)
    print(tabulate(summary_rows, headers="keys", tablefmt="simple", floatfmt=".2f"))
