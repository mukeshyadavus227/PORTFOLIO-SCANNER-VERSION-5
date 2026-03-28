"""
Indicator calculations matching Pine Script's ta.* functions.

All functions take a DataFrame (with OHLCV columns) or a Series and return
a Series or tuple of Series.  Smoothing methods replicate Pine Script exactly:
  - RMA (Wilder's): alpha = 1/period,  rma[i] = alpha * x[i] + (1 - alpha) * rma[i-1]
  - EMA:            alpha = 2/(period+1), same recursive formula
  - SMA:            simple rolling mean
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════
# Core smoothing primitives
# ═══════════════════════════════════════════════════════════════════════════

def _rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's RMA (Pine Script's ta.rma).

    First value is seeded with SMA, then:
        rma[i] = (1/period) * x[i]  +  (1 - 1/period) * rma[i-1]
    """
    alpha = 1.0 / period
    values = series.to_numpy(dtype=float)
    out = np.full_like(values, np.nan)

    # Seed: SMA of first `period` non-NaN values
    first_valid = 0
    while first_valid < len(values) and np.isnan(values[first_valid]):
        first_valid += 1
    seed_end = first_valid + period
    if seed_end > len(values):
        return pd.Series(out, index=series.index)

    out[seed_end - 1] = np.mean(values[first_valid:seed_end])
    for i in range(seed_end, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]

    return pd.Series(out, index=series.index)


# ═══════════════════════════════════════════════════════════════════════════
# 1. EMA
# ═══════════════════════════════════════════════════════════════════════════

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average (Pine Script's ta.ema).

    Seeded with SMA, then alpha = 2 / (period + 1).
    """
    alpha = 2.0 / (period + 1)
    values = series.to_numpy(dtype=float)
    out = np.full_like(values, np.nan)

    first_valid = 0
    while first_valid < len(values) and np.isnan(values[first_valid]):
        first_valid += 1
    seed_end = first_valid + period
    if seed_end > len(values):
        return pd.Series(out, index=series.index)

    out[seed_end - 1] = np.mean(values[first_valid:seed_end])
    for i in range(seed_end, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]

    return pd.Series(out, index=series.index)


# ═══════════════════════════════════════════════════════════════════════════
# 2. SMA
# ═══════════════════════════════════════════════════════════════════════════

def calc_sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average (Pine Script's ta.sma)."""
    return series.rolling(window=period, min_periods=period).mean()


# ═══════════════════════════════════════════════════════════════════════════
# 3. RSI  — Wilder's RMA, NOT SMA
# ═══════════════════════════════════════════════════════════════════════════

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI using RMA smoothing (Pine Script's ta.rsi).

    RSI = 100 - 100 / (1 + avg_gain / avg_loss)
    where avg_gain and avg_loss use Wilder's RMA.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = _rma(gain, period)
    avg_loss = _rma(loss, period)

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is 0 -> RS is inf -> RSI = 100
    rsi = rsi.fillna(100.0)
    # Restore leading NaNs
    rsi.iloc[:period] = np.nan
    return rsi


# ═══════════════════════════════════════════════════════════════════════════
# 4. ATR
# ═══════════════════════════════════════════════════════════════════════════

def _true_range(df: pd.DataFrame) -> pd.Series:
    """True Range (Pine Script's ta.tr)."""
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range using RMA (Pine Script's ta.atr)."""
    tr = _true_range(df)
    return _rma(tr, period)


# ═══════════════════════════════════════════════════════════════════════════
# 5. ADX  with +DI and -DI
# ═══════════════════════════════════════════════════════════════════════════

def calc_adx(df: pd.DataFrame, period: int = 14,
             smoothing: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """ADX, +DI, -DI (Pine Script's ta.dmi).

    Returns (plus_di, minus_di, adx).
    All smoothing is Wilder's RMA.
    """
    high = df["High"]
    low = df["Low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    atr = calc_atr(df, period)
    smooth_plus = _rma(plus_dm, period)
    smooth_minus = _rma(minus_dm, period)

    plus_di = 100.0 * smooth_plus / atr
    minus_di = 100.0 * smooth_minus / atr

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = _rma(dx, smoothing)

    return plus_di, minus_di, adx


# ═══════════════════════════════════════════════════════════════════════════
# 6. Stochastic  %K and %D
# ═══════════════════════════════════════════════════════════════════════════

def calc_stochastic(df: pd.DataFrame, k_period: int = 14,
                    k_smooth: int = 3,
                    d_smooth: int = 3) -> tuple[pd.Series, pd.Series]:
    """Stochastic Oscillator (Pine Script's ta.stoch).

    %K = SMA( (close - lowest_low) / (highest_high - lowest_low) * 100, k_smooth )
    %D = SMA(%K, d_smooth)
    """
    lowest = df["Low"].rolling(k_period).min()
    highest = df["High"].rolling(k_period).max()

    raw_k = 100.0 * (df["Close"] - lowest) / (highest - lowest).replace(0, np.nan)
    k = raw_k.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    return k, d


# ═══════════════════════════════════════════════════════════════════════════
# 7. MACD
# ═══════════════════════════════════════════════════════════════════════════

def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26,
              signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD (Pine Script's ta.macd).

    Returns (macd_line, signal_line, histogram).
    """
    fast_ema = calc_ema(series, fast)
    slow_ema = calc_ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ═══════════════════════════════════════════════════════════════════════════
# 8. Bollinger Bands
# ═══════════════════════════════════════════════════════════════════════════

def calc_bollinger(series: pd.Series, period: int = 20,
                   mult: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands (Pine Script's ta.bb).

    Returns (upper, middle, lower).
    """
    middle = calc_sma(series, period)
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + mult * std
    lower = middle - mult * std
    return upper, middle, lower


# ═══════════════════════════════════════════════════════════════════════════
# 9. VWAP
# ═══════════════════════════════════════════════════════════════════════════

def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP with daily reset (Pine Script's ta.vwap).

    Falls back to VWMA(20) when Volume is missing or all zeros.
    """
    if "Volume" not in df.columns or (df["Volume"] == 0).all():
        # Fallback: VWMA-like using SMA on typical price
        tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
        return calc_sma(tp, 20)

    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0

    # Group by calendar date for daily reset
    date_groups = df.index.date
    cum_tp_vol = (tp * df["Volume"]).groupby(date_groups).cumsum()
    cum_vol = df["Volume"].groupby(date_groups).cumsum()

    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    return vwap


# ═══════════════════════════════════════════════════════════════════════════
# 10. SuperTrend
# ═══════════════════════════════════════════════════════════════════════════

def calc_supertrend(df: pd.DataFrame, period: int = 10,
                    multiplier: float = 3.0) -> tuple[pd.Series, pd.Series]:
    """SuperTrend indicator.

    Returns (direction, value) where direction is +1 (bullish) or -1 (bearish).
    """
    atr = calc_atr(df, period)
    hl2 = (df["High"] + df["Low"]) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    n = len(df)
    close = df["Close"].to_numpy(dtype=float).copy()
    upper = upper_basic.to_numpy(dtype=float).copy()
    lower = lower_basic.to_numpy(dtype=float).copy()
    direction = np.full(n, np.nan)
    st_value = np.full(n, np.nan)

    # Find first bar with valid ATR
    start = 0
    while start < n and np.isnan(upper[start]):
        start += 1
    if start >= n:
        return (
            pd.Series(direction, index=df.index),
            pd.Series(st_value, index=df.index),
        )

    # Seed: assume bullish at first valid bar
    direction[start] = 1.0
    st_value[start] = lower[start]

    for i in range(start + 1, n):
        # Final upper band: only tighten, never widen downward
        if not (upper[i] < upper[i - 1] or close[i - 1] > upper[i - 1]):
            upper[i] = upper[i - 1]

        # Final lower band: only tighten, never widen upward
        if not (lower[i] > lower[i - 1] or close[i - 1] < lower[i - 1]):
            lower[i] = lower[i - 1]

        # Direction flip
        prev_dir = direction[i - 1]
        if prev_dir == -1.0 and close[i] > upper[i]:
            direction[i] = 1.0
        elif prev_dir == 1.0 and close[i] < lower[i]:
            direction[i] = -1.0
        else:
            direction[i] = prev_dir

        st_value[i] = lower[i] if direction[i] == 1.0 else upper[i]

    return (
        pd.Series(direction, index=df.index),
        pd.Series(st_value, index=df.index),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 11. Range Filter
# ═══════════════════════════════════════════════════════════════════════════

def calc_range_filter(series: pd.Series, period: int = 100,
                      multiplier: float = 3.0) -> pd.Series:
    """Range Filter (smoothrng / rngfilt from V5-style scripts).

    smoothrng = RMA(|close - close[1]|, period) * multiplier
    rngfilt:   walk the filter toward price, clamped by smoothrng.
    """
    abs_change = series.diff().abs()
    smooth_rng = _rma(abs_change, period) * multiplier

    src = series.to_numpy(dtype=float)
    rng = smooth_rng.to_numpy(dtype=float)
    filt = np.full_like(src, np.nan)

    # Seed at first valid smooth_rng value
    start = 0
    while start < len(rng) and np.isnan(rng[start]):
        start += 1
    if start >= len(src):
        return pd.Series(filt, index=series.index)

    filt[start] = src[start]
    for i in range(start + 1, len(src)):
        if np.isnan(rng[i]):
            filt[i] = filt[i - 1]
            continue
        prev = filt[i - 1]
        if src[i] > prev:
            filt[i] = max(prev, src[i] - rng[i])
        else:
            filt[i] = min(prev, src[i] + rng[i])

    return pd.Series(filt, index=series.index)


# ═══════════════════════════════════════════════════════════════════════════
# 12. Choppiness Index
# ═══════════════════════════════════════════════════════════════════════════

def calc_choppiness_index(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Choppiness Index (exact Pine Script formula from V5).

    chop = 100 * log10( sum(TR, n) / (highest_high - lowest_low) ) / log10(n)
    """
    tr = _true_range(df)
    sum_tr = tr.rolling(period).sum()
    highest = df["High"].rolling(period).max()
    lowest = df["Low"].rolling(period).min()
    hl_range = (highest - lowest).replace(0, np.nan)

    chop = 100.0 * np.log10(sum_tr / hl_range) / math.log10(period)
    return chop


# ═══════════════════════════════════════════════════════════════════════════
# 13. Waddah Attar Explosion
# ═══════════════════════════════════════════════════════════════════════════

def calc_waddah_attar(df: pd.DataFrame, sensitivity: float = 150.0,
                      fast: int = 20, slow: int = 40,
                      bb_len: int = 20,
                      bb_mult: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Waddah Attar Explosion.

    Returns (explosion, dead_zone, trend_direction).
    - explosion:  abs( MACD-diff ) * sensitivity  (magnitude of move)
    - dead_zone:  Bollinger Band Width as a volatility threshold
    - trend_direction: +1 when MACD diff expanding bullish, -1 bearish
    """
    close = df["Close"]

    macd_fast = calc_ema(close, fast)
    macd_slow = calc_ema(close, slow)
    diff_now = macd_fast - macd_slow
    diff_prev = diff_now.shift(1)

    explosion = (diff_now - diff_prev).abs() * sensitivity

    # Dead zone = BB upper - BB lower
    upper, _mid, lower = calc_bollinger(close, bb_len, bb_mult)
    dead_zone = upper - lower

    trend_direction = pd.Series(
        np.where(diff_now > diff_prev, 1.0, -1.0),
        index=df.index,
    )

    return explosion, dead_zone, trend_direction


# ═══════════════════════════════════════════════════════════════════════════
# CLI test harness
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from data_loader import load_sierra_dly

    spy = load_sierra_dly("data/SPY.dly")
    print(f"SPY: {len(spy)} rows, {spy.index.min().date()} → {spy.index.max().date()}\n")

    close = spy["Close"]

    # ── EMA / SMA ──
    spy["EMA_21"] = calc_ema(close, 21)
    spy["SMA_200"] = calc_sma(close, 200)

    # ── RSI ──
    spy["RSI_14"] = calc_rsi(close, 14)

    # ── ATR ──
    spy["ATR_14"] = calc_atr(spy, 14)

    # ── ADX ──
    spy["+DI"], spy["-DI"], spy["ADX_14"] = calc_adx(spy, 14, 14)

    # ── Stochastic ──
    spy["%K"], spy["%D"] = calc_stochastic(spy, 14, 3, 3)

    # ── MACD ──
    spy["MACD"], spy["Signal"], spy["Hist"] = calc_macd(close, 12, 26, 9)

    # ── Bollinger Bands ──
    spy["BB_Upper"], spy["BB_Mid"], spy["BB_Lower"] = calc_bollinger(close, 20, 2.0)

    # ── VWAP ──
    spy["VWAP"] = calc_vwap(spy)

    # ── SuperTrend ──
    spy["ST_Dir"], spy["ST_Val"] = calc_supertrend(spy, 10, 3.0)

    # ── Range Filter ──
    spy["RngFilt"] = calc_range_filter(close, 100, 3.0)

    # ── Choppiness Index ──
    spy["Chop"] = calc_choppiness_index(spy, 14)

    # ── Waddah Attar ──
    spy["WAE_Expl"], spy["WAE_Dead"], spy["WAE_Dir"] = calc_waddah_attar(spy)

    # ── Print last 5 rows of each indicator ──
    indicators = {
        "EMA(21)":    spy["EMA_21"],
        "SMA(200)":   spy["SMA_200"],
        "RSI(14)":    spy["RSI_14"],
        "ATR(14)":    spy["ATR_14"],
        "+DI(14)":    spy["+DI"],
        "-DI(14)":    spy["-DI"],
        "ADX(14)":    spy["ADX_14"],
        "%K":         spy["%K"],
        "%D":         spy["%D"],
        "MACD":       spy["MACD"],
        "Signal":     spy["Signal"],
        "Histogram":  spy["Hist"],
        "BB Upper":   spy["BB_Upper"],
        "BB Mid":     spy["BB_Mid"],
        "BB Lower":   spy["BB_Lower"],
        "VWAP":       spy["VWAP"],
        "ST Dir":     spy["ST_Dir"],
        "ST Value":   spy["ST_Val"],
        "RangeFilter": spy["RngFilt"],
        "Chop(14)":   spy["Chop"],
        "WAE Expl":   spy["WAE_Expl"],
        "WAE Dead":   spy["WAE_Dead"],
        "WAE Dir":    spy["WAE_Dir"],
    }

    for name, s in indicators.items():
        tail = s.tail(5)
        print(f"--- {name} ---")
        for dt, val in tail.items():
            print(f"  {dt.date()}  {val:>12.4f}")
        print()

    # ── Spot-check RSI and ATR ──
    print("=" * 60)
    print("SPOT CHECK — last value vs expected TradingView range")
    print("=" * 60)
    last_rsi = spy["RSI_14"].iloc[-1]
    last_atr = spy["ATR_14"].iloc[-1]
    last_close = close.iloc[-1]
    print(f"  RSI(14):  {last_rsi:.2f}  (expect 30-70 typical range)")
    print(f"  ATR(14):  {last_atr:.2f}  (expect ~1-3% of price)")
    print(f"  ATR/Close: {last_atr/last_close*100:.2f}%")
    print(f"  Close:    {last_close:.2f}")
