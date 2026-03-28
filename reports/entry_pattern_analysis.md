# Entry Pattern Deep Dive

*1280 trades across 37 tickers, with indicator values captured at entry*

## 1. LONG-ONLY Deep Dive (trending_up regime)

*520 long entries in trending_up across all tickers*

### RSI Range at Entry

| RSI Range | Trades | WR% | Avg PnL | Total PnL |
|-----------|--------|-----|---------|-----------|
| 35-45 | 5 | 20.0 | $-39.27 | $-196.36 |
| 40-50 | 23 | 13.0 | $-59.93 | $-1378.46 |
| 45-55 | 98 | 28.6 | $-14.46 | $-1416.65 |
| 50-60 | 204 | 32.8 | $-1.88 | $-383.55 |
| 55-65 | 264 | 35.2 | $2.93 | $772.36 |
| 60-70 | 235 | 42.6 | $23.34 | $5485.63 |

### ADX Range at Entry

| ADX Range | Trades | WR% | Avg PnL | Total PnL |
|-----------|--------|-----|---------|-----------|
| 25-30 | 239 | 37.2 | $9.25 | $2211.72 |
| 30-35 | 113 | 38.9 | $13.05 | $1474.19 |
| 35-40 | 58 | 41.4 | $18.64 | $1081.24 |
| 40-50 | 57 | 38.6 | $10.92 | $622.71 |
| 50+ | 16 | 43.8 | $30.55 | $488.72 |

### EMA9/EMA21 Crossover Timing

| Bars Since Cross | Trades | WR% | Avg PnL |
|------------------|--------|-----|---------|
| Cross day | 488 | 38.9 | $13.60 |
| 4-9 bars after | 5 | 40.0 | $18.54 |
| 10+ bars after | 27 | 25.9 | $-20.36 |

### Pullback Depth (% below 20-bar high)

| Pullback % | Trades | WR% | Avg PnL |
|------------|--------|-----|---------|
| 0-1% | 98 | 51.0 | $48.17 |
| 1-3% | 188 | 41.5 | $20.69 |
| 3-5% | 120 | 28.3 | $-13.65 |
| 5-8% | 89 | 30.3 | $-13.49 |
| 8-15% | 22 | 36.4 | $8.65 |

## 2. BREAKOUT Deep Dive (S3 on volatile regime)

*261 S3 breakout entries in volatile regime*

Focus tickers (AAPL, MU, TSLA, EWZ, NVDA): 44 trades

### WAE Confirmation Value

| Condition | Trades | WR% | Avg PnL | Total PnL |
|-----------|--------|-----|---------|-----------|
| WAE active (expl > dead) | 259 | 29.0 | $-15.38 | $-3983.38 |

### Volume-Only vs Volume+WAE

| Filter | Trades | WR% | Avg PnL |
|--------|--------|-----|---------|
| Volume above avg only | 154 | 32.5 | $-4.30 |
| Volume + WAE active | 152 | 32.2 | $-5.01 |

### Donchian Period Note

Current system uses Donchian(20). Testing alternate periods (10, 15, 30)
would require re-running the strategy engine with modified parameters.
Recommendation: the 20-period default aligns with the Pine Script V5
and produces the existing breakout results. Consider testing in a
parameter sweep phase.

## 3. SHORT Signal Investigation

*642 total short entries*
*Overall short WR: 23.2%*

### Restrictive Short Filters

| Filter | Trades | WR% | Avg PnL | Total PnL |
|--------|--------|-----|---------|-----------|
| All shorts | 642 | 23.2 | $-30.71 | $-19717.77 |
| ADX > 30 | 230 | 23.9 | $-28.60 | $-6578.96 |
| ADX > 35 | 114 | 28.9 | $-17.10 | $-1949.85 |
| ADX > 40 | 52 | 26.9 | $-22.04 | $-1146.31 |
| EMA9 < EMA21 | 620 | 22.4 | $-32.62 | $-20226.17 |
| Close < EMA200 | 461 | 22.8 | $-32.01 | $-14758.02 |

**Verdict:** No short filter combination achieves 40% WR. Best found: ADX > 35 (28.9% WR). **Recommend disabling shorts entirely** or restricting to extreme conditions only.

## 4. COMPOSITE SCORE REBUILD

### New Weights (evidence-based)

| Component | Old Weight | New Weight | Justification |
|-----------|-----------|-----------|---------------|
| EMA9 > EMA21 | 15 | **25** | +15.3% WR delta (strongest) |
| RSI direction | 10 | **25** | +15.1% WR delta |
| Close vs EMA200 | 15 | **20** | +9.8% WR delta |
| Weekly trend (EMA50 slope) | — | **15** | Structural trend proxy |
| Volume > SMA(20) | 10 | **5** | -1.2% delta (near zero) |
| MACD direction | 10 | **5** | +5.3% delta (moderate) |
| Stoch/ADX/Chop | 30 combined | **5** | Near-zero predictive value |
| Range Filter | 15 | **0** | Redundant with EMA9/21 |
| VWAP position | 10 | **0** | Redundant with EMA200 |

### Threshold Comparison: Old vs New Scoring

| Threshold | Old: Trades | Old: WR% | Old: PF | New: Trades | New: WR% | New: PF |
|-----------|-------------|----------|---------|-------------|----------|---------|
| >= 60 | 816 | 29.5 | 0.80 | 1230 | 30.2 | 0.84 |
| >= 65 | 697 | 28.7 | 0.78 | 1158 | 30.2 | 0.84 |
| >= 70 | 494 | 29.1 | 0.80 | 1077 | 30.3 | 0.84 |
| >= 75 | 270 | 27.8 | 0.75 | 1052 | 30.6 | 0.85 |
| >= 80 | 177 | 27.7 | 0.74 | 1006 | 31.0 | 0.87 |
| >= 85 | 66 | 36.4 | 1.08 | 929 | 31.2 | 0.88 |

**Best new threshold:** >= 85 (PF=0.88)

## 5. Definitive Entry Profiles

### Cluster A: Trend Longs

- **Regime:** trending_up only
- **Direction:** LONG only
- **Optimal RSI:** 55-65 (35.2% WR, 264 trades)
- **Optimal ADX:** 35-40 (41.4% WR, 58 trades)
- **Optimal pullback:** 0-2 (47.7% WR, 197 trades)
- **Required:** EMA9 > EMA21, RSI > 50, Close > EMA200

### Cluster B: Breakout Longs

- **Regime:** volatile
- **Direction:** LONG only
- **Strategy:** S3_BreakoutMomentum
- **Donchian:** 20-period (default)
- **Volume:** Required (above 20-SMA avg)
- **Best tickers:** AAPL, MU, TSLA, EWZ (50-60% WR)

### Cluster C: Shorts

- **Status:** **DISABLED** — recommend removing all short signals
- **Reason:** Overall short WR = 23.2%. No filter combination tested achieves 40% WR.
- **Impact:** Removing shorts eliminates ~50% of trades but removes the primary source of losses.
