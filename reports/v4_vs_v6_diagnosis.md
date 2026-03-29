# V4 vs V6 Signal Frequency Diagnosis

*Why V6 generates 0.6 trades/year on SPY while V4 generates 2-4/month*

## 1. V6 Signal Gate Diagnosis

### Per-Condition Pass Rates (SPY, last 500 bars, 2024-2026)

| Condition | Pass Rate | Verdict |
|-----------|-----------|---------|
| Close > EMA200 | 91.4% | Not restrictive |
| Weekly Bullish | 90.4% | Not restrictive |
| EMA9 > EMA50 | 81.2% | Not restrictive |
| Volume > volSMA*0.8 | 75.8% | Not restrictive |
| RSI 55-80 | 59.6% | Moderate filter |
| Close within 1% of 20-bar high | 51.0% | Moderate filter |
| **ADX > 30** | **15.2%** | **BOTTLENECK #1** |
| **Regime = trending_up** | **4.4%** | **BOTTLENECK #2** |
| **All 8 combined** | **2.0%** | **10 bars out of 500** |

### The Cascade Effect

Stacking the first 6 conditions (EMA, RSI, near-high, EMA200, volume, weekly) still leaves 157 bars (31.4%). Adding ADX > 30 annihilates this to just 10 bars. The regime gate adds zero further filtering because regime=trending_up already requires ADX > 30.

### Root Cause

**ADX > 30 is the universal killer.** SPY spends only 15% of time with ADX above 30, and only 4.4% in the full trending_up regime (ADX>30 + positive DI + above EMA200). V6 requires ALL of these plus 5 more conditions simultaneously. The result: ~20 trades across 33 years of SPY data.

## 2. V4 Entry Logic Analysis

V4 uses 4 parallel sub-strategies that **compete independently**. Each has its own regime gate (but relaxed — allows "adjacent" regimes), its own scoring, and its own entry conditions. The winner is whoever scores highest on each bar.

### S3: EMA/VWAP Momentum (V4's most prolific signal generator)

**Entry trigger:** EMA(9) crosses above EMA(21) within the last 5 bars
**Hard gates:** RSI not blocked (RSI < 70 for longs), recent EMA cross required
**Scoring (additive, no all-must-be-true gate):**
- EMA cross event: 25 pts (or 10 if just EMA9 > EMA21 without fresh cross)
- Close > VWAP/SMA20 proxy: 15 pts
- Close > EMA(50): 12 pts
- MACD histogram positive + RSI > 50: 15 pts (or 8 if just MACD positive)
- Volume above average: 10 pts
- ROC(20d) > 3%: 8 pts
- Regime alignment: 5-15 pts

**Max possible: ~100 pts. Minimum to reach 75: need ~4-5 conditions met**
**Regime gate: works in MOMENTUM, TRENDING, BREAKOUT, and NEUTRAL** — very permissive

### S4: Multi-TF Trend (V4's pullback strategy)

**Entry trigger:** RSI pullback to 25-40 zone OR price bounces off EMA(21)
**Hard gate:** At least one daily entry trigger (pullback OR bounce)
**Scoring (additive):**
- Weekly trend bullish: 25 pts
- Weekly ADX > 20: 10 pts
- Pullback buy (RSI 25-40): 20 pts / EMA bounce: 15 pts
- MACD above signal: 8 pts
- Close > SMA200: 8 pts
- Volume above average: 7 pts
- ROC(60d) > 5%: 7 pts
- Regime alignment: 5-15 pts

**Max possible: ~100 pts. Minimum to reach 75: weekly bull + pullback + 2-3 others**
**Regime gate: works in TRENDING and NEUTRAL** — moderately permissive

### Key V4 Design Differences from V6

| Feature | V4 | V6 |
|---------|----|----|
| Entry architecture | **Additive scoring** — no hard all-must-be-true gate | **Conjunctive gate** — ALL 8 conditions required before scoring starts |
| ADX relationship | ADX used as **scoring bonus** (ADX>25: +15pts) | ADX>30 as **hard gate** (kills signal if not met) |
| Regime requirement | Adjacent regimes allowed (S3 works in 4 of 5 regimes) | Strict trending_up only |
| EMA cross | **Event-based trigger** — fires within 5 bars of cross | State-based — only checks if EMA9 > EMA50 currently |
| Pullback logic | RSI pullback to 25-40 OR EMA bounce triggers S4 | No pullback mechanism — requires near highs only |
| Signal diversity | 4 strategies compete independently | 1 strategy (Mode A) dominates; Mode B extremely rare |

## 3. V4 vs V6 Signal Count Comparison (SPY 2024-2026)

| Metric | V4 (S3+S4) | V6 (Mode A) |
|--------|-----------|-------------|
| Bars with score > 0 | 127 | 10 |
| Score >= 60 | 42 | 0 |
| Score >= 65 | 41 | 0 |
| Score >= 75 | 20 | 0 |
| Signals/year | ~16 | **0** |

### Where V4 Fires but V6 Doesn't (20 bars)

V6 condition failure on ALL 20 V4-signal bars:
- **ADX > 30: fails on 20/20** (100%) — the universal bottleneck
- **Regime = trending_up: fails on 20/20** (because regime requires ADX > 30)
- Weekly bullish: fails on 20/20 (likely weekly EMA200 warmup issue on sliced data)
- Close > EMA200: fails on 9/20
- Near-high (1%): fails on 5/20
- RSI 55-80: fails on 3/20
- EMA9 > EMA50: fails on 3/20

## 4. Recommended V6 Entry Logic Rebuild

### Problem Summary
V6's "all 8 conditions must be true simultaneously" architecture is fundamentally incompatible with generating 2-4 signals/month. The conditions are individually reasonable but multiplicatively impossible.

### Recommended Changes

#### A. Replace conjunctive gate with V4-style additive scoring

**Current V6:** All 8 conditions must be TRUE before scoring even starts.
**Proposed:** Use V4's approach — scoring is always active, conditions just add or subtract points. The composite threshold does the filtering.

#### B. Demote ADX from hard gate to scoring bonus

**Current:** ADX > 30 required (hard gate)
**Proposed:**
- ADX > 30: +10 pts (strong trend bonus)
- ADX > 25: +5 pts (moderate trend)
- ADX < 20: -10 pts (penalty for choppy market)

This alone would increase signal frequency ~6x while still rewarding strong trends.

#### C. Relax regime to "trending_up OR bullish_momentum"

**Current:** Strict trending_up (ADX>30 + positive DI + above EMA200)
**Proposed:** Fire when close > EMA200 AND (EMA9 > EMA50 OR positive DI). Drop the ADX requirement from the regime entirely.

#### D. Add V4's pullback-to-EMA trigger (S4 logic)

V6 only looks for "near highs" entries. Add an alternative trigger:
- RSI pulls back to 40-55 zone AND price bounces off EMA(21) or EMA(50)
- This catches the pullback entries V4 excels at

#### E. Add V4's EMA cross event trigger (S3 logic)

V6 checks if EMA9 > EMA50 (state). V4 checks if EMA9 **recently crossed above** EMA21 (event within 5 bars). The event trigger is more selective and timely.

#### F. Relax near-highs threshold

**Current:** Within 1% of 20-bar high
**Proposed:** Within 3-5% — or make this a scoring component instead of a gate

#### G. Lower composite minimum to 60

The evidence-weighted scoring system already separates quality from noise. With the gate removed, a 60-point threshold on the additive score should produce 2-4 signals/month with reasonable quality.

### Expected Signal Count After Changes

| Change | Estimated SPY signals 2024-2026 | Notes |
|--------|--------------------------------|-------|
| Current V6 | 0 | Dead |
| Remove ADX hard gate only | ~10 | Still sparse |
| + Relax regime | ~25 | Close to target |
| + Add pullback trigger | ~40 | Two entry types |
| + Lower threshold to 60 | ~50 | 2-3/month |
| + 5-bar cooldown | ~35 after cooldown | **2/month — viable** |

### Proposed Hybrid Architecture

```
Signal = max(Mode_A_score, Mode_B_score, Pullback_score)

Mode_A (Trend Continuation):
  Base: EMA9 > EMA_slow AND close > EMA200 → 25+20 = 45 base
  Bonuses: RSI 55-70 (+25), Weekly bullish (+15), MACD+ (+5), Vol (+5), ADX>25 (+5)
  NO hard gates except close > EMA200
  Minimum score: 60

Mode_B (Breakout):
  Same as current — Donchian break + volume spike

Pullback (NEW — from V4's S4):
  Trigger: RSI drops to 35-50 AND close bounces off EMA(21) from below
  Base: Weekly bullish (+25), pullback trigger (+20) = 45 base
  Bonuses: MACD+ (+8), close > SMA200 (+8), Vol (+7), ADX>25 (+5), ROC>5% (+7)
  Minimum score: 60
```

This hybrid keeps V6's evidence-weighted scoring, regime detection, and weekly MTF confirmation while adopting V4's signal diversity and additive architecture.
