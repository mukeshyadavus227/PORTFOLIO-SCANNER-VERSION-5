"""
Winner selection and composite fire logic for Portfolio Scanner V5.

Picks the best signal across all 4 sub-strategies on each bar, applies
alignment checks, signal expiry, and alternating-direction enforcement.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicators import calc_ema, calc_macd, calc_rsi, calc_sma
from strategies import ALL_STRATEGIES, compute_all_indicators
from regime import detect_regime


# ═══════════════════════════════════════════════════════════════════════════
# 1. Alignment score
# ═══════════════════════════════════════════════════════════════════════════

def calculate_alignment(strategies_output: dict[str, pd.DataFrame],
                        df: pd.DataFrame,
                        ind: dict[str, pd.Series]) -> pd.Series:
    """Compute per-bar alignment score (0-100).

    Measures how many confirmation filters agree with the dominant signal
    direction on that bar.  Direction is determined by whichever strategy
    has the strongest signal.
    """
    close = df["Close"]
    idx = df.index

    # Determine dominant direction per bar: +1 long, -1 short, 0 none
    best_long = pd.Series(0.0, index=idx)
    best_short = pd.Series(0.0, index=idx)
    for _name, sig in strategies_output.items():
        best_long = best_long.where(
            best_long >= sig["signal_strength"].where(sig["long_signal"], 0.0),
            sig["signal_strength"].where(sig["long_signal"], 0.0),
        )
        best_short = best_short.where(
            best_short >= sig["signal_strength"].where(sig["short_signal"], 0.0),
            sig["signal_strength"].where(sig["short_signal"], 0.0),
        )

    direction = pd.Series(
        np.where(best_long >= best_short, 1.0, -1.0),
        index=idx,
    )
    has_signal = (best_long > 0) | (best_short > 0)

    # ── Confirmation filters ──
    ema200 = ind["ema200"]
    rf = ind["range_filter"]
    macd_line = ind["macd_line"]
    signal_line = ind["signal_line"]
    rsi = ind["rsi14"]
    adx = ind["adx"]
    stoch_k = ind["stoch_k"]
    vwap = ind["vwap"]
    chop = ind["chop"]

    score = pd.Series(0.0, index=idx)

    # EMA(200) filter: +15 — price above for long, below for short
    ema_agree = np.where(direction > 0, close > ema200, close < ema200)
    score += np.where(ema_agree, 15.0, 0.0)

    # Range Filter direction: +15 — price above RF for long, below for short
    rf_agree = np.where(direction > 0, close > rf, close < rf)
    score += np.where(rf_agree, 15.0, 0.0)

    # RQK direction (use EMA9 vs EMA21 as proxy): +15
    ema9 = ind["ema9"]
    ema21 = ind["ema21"]
    rqk_agree = np.where(direction > 0, ema9 > ema21, ema9 < ema21)
    score += np.where(rqk_agree, 15.0, 0.0)

    # MACD direction: +10
    macd_agree = np.where(direction > 0, macd_line > signal_line, macd_line < signal_line)
    score += np.where(macd_agree, 10.0, 0.0)

    # RSI not in opposing zone: +10
    # Long: RSI not oversold-extreme (<20) is fine; Short: RSI not overbought-extreme (>80)
    rsi_ok = np.where(direction > 0, rsi > 30, rsi < 70)
    score += np.where(rsi_ok, 10.0, 0.0)

    # ADX above threshold (25): +10
    score += np.where(adx > 25, 10.0, 0.0)

    # Stochastic direction: +10
    stoch_agree = np.where(direction > 0, stoch_k > 30, stoch_k < 70)
    score += np.where(stoch_agree, 10.0, 0.0)

    # VWAP position: +10
    vwap_agree = np.where(direction > 0, close > vwap, close < vwap)
    score += np.where(vwap_agree, 10.0, 0.0)

    # Choppiness context: +5
    # For trend strategies: chop < 61.8 is good; for range: chop > 61.8
    # Use a blend: reward when chop aligns with the signal type
    chop_ok = np.where(adx > 25, chop < 61.8, chop > 61.8)
    score += np.where(chop_ok, 5.0, 0.0)

    # Zero alignment where no signal exists
    alignment = pd.Series(np.where(has_signal, score, 0.0), index=idx)
    return alignment


# ═══════════════════════════════════════════════════════════════════════════
# 2. Winner selection
# ═══════════════════════════════════════════════════════════════════════════

def select_winner(strategies_output: dict[str, pd.DataFrame],
                  alignment: pd.Series,
                  min_composite: float = 50.0) -> pd.DataFrame:
    """Select the winning strategy on each bar.

    Composite = signal_strength * alignment.
    Winner = strategy with highest composite; must exceed min_composite.

    Returns DataFrame with columns:
        winner_strategy, direction, composite_score, num_confirming
    """
    idx = alignment.index
    n = len(idx)

    # Build composite scores per strategy
    composites = {}
    for name, sig in strategies_output.items():
        composites[name] = sig["signal_strength"] * alignment

    # Find winner per bar
    winner_strategy = pd.Series("", index=idx, dtype="object")
    direction = pd.Series("", index=idx, dtype="object")
    composite_score = pd.Series(0.0, index=idx)
    num_confirming = pd.Series(0, index=idx, dtype=int)

    # Vectorize: stack composites and pick max
    strat_names = list(strategies_output.keys())
    comp_matrix = np.column_stack([composites[n].to_numpy() for n in strat_names])

    best_idx = np.argmax(comp_matrix, axis=1)
    best_score = np.max(comp_matrix, axis=1)

    for i in range(n):
        if best_score[i] < min_composite:
            continue
        sname = strat_names[best_idx[i]]
        sig = strategies_output[sname]
        composite_score.iat[i] = best_score[i]
        winner_strategy.iat[i] = sname

        if sig["long_signal"].iat[i]:
            direction.iat[i] = "long"
        elif sig["short_signal"].iat[i]:
            direction.iat[i] = "short"
        else:
            # Score came from strength residual; no active signal
            winner_strategy.iat[i] = ""
            composite_score.iat[i] = 0.0
            continue

        # Count how many strategies have a signal in the same direction
        count = 0
        for sn, s in strategies_output.items():
            if direction.iat[i] == "long" and s["long_signal"].iat[i]:
                count += 1
            elif direction.iat[i] == "short" and s["short_signal"].iat[i]:
                count += 1
        num_confirming.iat[i] = count

    return pd.DataFrame({
        "winner_strategy": winner_strategy,
        "direction": direction,
        "composite_score": composite_score,
        "num_confirming": num_confirming,
    }, index=idx)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Signal expiry
# ═══════════════════════════════════════════════════════════════════════════

def apply_signal_expiry(signals: pd.DataFrame,
                        expiry_bars: int = 3) -> pd.DataFrame:
    """Expire signals older than expiry_bars.

    A signal "starts" when winner_strategy transitions from empty to non-empty.
    It stays valid for expiry_bars consecutive candles.  After that, it expires
    unless a new signal fires.

    Adds column: signal_age (int, 0 = no signal)
    """
    out = signals.copy()
    n = len(out)
    age = np.zeros(n, dtype=int)

    for i in range(n):
        if out["winner_strategy"].iat[i] == "":
            age[i] = 0
            continue

        if i == 0 or out["winner_strategy"].iat[i - 1] == "":
            # New signal starts
            age[i] = 1
        elif (out["winner_strategy"].iat[i] == out["winner_strategy"].iat[i - 1]
              and out["direction"].iat[i] == out["direction"].iat[i - 1]):
            # Continuation of same signal
            age[i] = age[i - 1] + 1
        else:
            # Different strategy/direction → new signal
            age[i] = 1

        # Expire if too old
        if age[i] > expiry_bars:
            out.at[out.index[i], "winner_strategy"] = ""
            out.at[out.index[i], "direction"] = ""
            out.at[out.index[i], "composite_score"] = 0.0
            out.at[out.index[i], "num_confirming"] = 0
            age[i] = 0

    out["signal_age"] = age
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 4. Alternating direction enforcement
# ═══════════════════════════════════════════════════════════════════════════

def apply_alternate_signal(signals: pd.DataFrame) -> pd.DataFrame:
    """Enforce alternating long/short — no consecutive same-direction entries.

    Consecutive signals in the same direction after the first are suppressed.
    A new signal group starts when direction changes or a gap (no signal) occurs
    followed by a new direction.
    """
    out = signals.copy()
    n = len(out)
    last_fired_dir = ""

    for i in range(n):
        d = out["direction"].iat[i]
        if d == "":
            continue

        if d == last_fired_dir:
            # Same direction as last fired → suppress
            out.at[out.index[i], "winner_strategy"] = ""
            out.at[out.index[i], "direction"] = ""
            out.at[out.index[i], "composite_score"] = 0.0
            out.at[out.index[i], "num_confirming"] = 0
            if "signal_age" in out.columns:
                out.at[out.index[i], "signal_age"] = 0
        else:
            last_fired_dir = d

    return out


# ═══════════════════════════════════════════════════════════════════════════
# Full pipeline helper
# ═══════════════════════════════════════════════════════════════════════════

def run_full_pipeline(df: pd.DataFrame,
                      min_composite: float = 50.0,
                      expiry_bars: int = 3) -> tuple[pd.DataFrame, dict]:
    """Run the complete pipeline: indicators → regime → strategies → scoring.

    Returns (final_signals DataFrame, metadata dict).
    """
    # 1. Indicators
    ind = compute_all_indicators(df)

    # 2. Regime
    regime = detect_regime(df, {
        "adx": ind["adx"],
        "plus_di": ind["plus_di"],
        "minus_di": ind["minus_di"],
        "atr": ind["atr"],
        "atr_sma20": ind["atr_sma20"],
        "chop": ind["chop"],
        "ema200": ind["ema200"],
    })

    # 3. Strategy signals
    strat_output = {}
    for strat in ALL_STRATEGIES:
        strat_output[strat.name] = strat.generate_signals(df, ind, regime)

    # 4. Alignment
    alignment = calculate_alignment(strat_output, df, ind)

    # 5. Winner selection
    raw_signals = select_winner(strat_output, alignment, min_composite)

    # 6. Signal expiry
    expired = apply_signal_expiry(raw_signals, expiry_bars)

    # 7. Alternating direction
    final = apply_alternate_signal(expired)

    return final, {
        "indicators": ind,
        "regime": regime,
        "strategies": strat_output,
        "alignment": alignment,
        "raw_signals": raw_signals,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Summary printer
# ═══════════════════════════════════════════════════════════════════════════

def print_pipeline_summary(ticker: str, final: pd.DataFrame, meta: dict) -> None:
    """Print a full summary of the scoring pipeline output."""
    fired = final[final["direction"] != ""]
    raw_fired = meta["raw_signals"][meta["raw_signals"]["direction"] != ""]

    print(f"\n{'=' * 65}")
    print(f"  COMPOSITE SCORING SUMMARY — {ticker}")
    print(f"{'=' * 65}")
    print(f"  Total bars:            {len(final):>6d}")
    print(f"  Raw signals (pre-filter): {len(raw_fired):>6d}  ({100*len(raw_fired)/len(final):.2f}%)")
    print(f"  Final signals (fired): {len(fired):>6d}  ({100*len(fired)/len(final):.2f}%)")

    if len(fired) == 0:
        print("  No signals fired above threshold.\n")
        return

    # Average composite score
    print(f"  Avg composite score:   {fired['composite_score'].mean():>6.1f}")
    print(f"  Max composite score:   {fired['composite_score'].max():>6.1f}")
    print()

    # Direction distribution
    dir_counts = fired["direction"].value_counts()
    print("  Direction distribution:")
    for d in ["long", "short"]:
        n = dir_counts.get(d, 0)
        print(f"    {d:>5s}: {n:>4d}  ({100*n/len(fired):.1f}%)")
    print()

    # Win distribution by strategy
    strat_counts = fired["winner_strategy"].value_counts()
    print("  Strategy win distribution:")
    rows = []
    for sname in sorted(strat_counts.index):
        n = strat_counts[sname]
        avg_cs = fired.loc[fired["winner_strategy"] == sname, "composite_score"].mean()
        rows.append({
            "Strategy": sname,
            "Wins": int(n),
            "%": round(100 * n / len(fired), 1),
            "Avg Score": round(avg_cs, 1),
        })
    print(tabulate(rows, headers="keys", tablefmt="simple", floatfmt=".1f"))
    print()

    # Confirming strategies breakdown
    confirm_counts = fired["num_confirming"].value_counts().sort_index()
    print("  Confirming strategies:")
    for k, v in confirm_counts.items():
        print(f"    {k} strategy(ies) confirming: {v} signals")
    print()

    # Last 10 signals
    recent = fired.tail(10)
    print("  Last 10 signals:")
    for dt, row in recent.iterrows():
        age_str = f"age={row['signal_age']}" if "signal_age" in row else ""
        print(f"    {dt.date()}  {row['direction']:>5s}  "
              f"score={row['composite_score']:.1f}  "
              f"strat={row['winner_strategy']}  "
              f"confirm={row['num_confirming']}  {age_str}")


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data_loader import load_sierra_dly

    tickers = [
        ("SPY", "data/SPY.dly"),
        ("QQQ", "data/QQQ.dly"),
    ]

    for ticker, path in tickers:
        df = load_sierra_dly(path)
        print(f"\nLoading {ticker}: {len(df)} rows, "
              f"{df.index.min().date()} → {df.index.max().date()}")

        final, meta = run_full_pipeline(df, min_composite=50.0, expiry_bars=3)
        print_pipeline_summary(ticker, final, meta)
