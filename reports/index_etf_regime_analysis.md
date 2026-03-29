# Index ETF Regime-Adaptive Analysis

*Testing longs in bull regime, shorts in bear regime, across full history*

## SPY

**Bull Regime Longs**: No viable params
**Bear Regime Shorts** (momentum_breakout): WR=88%, PF=7.02, n=8

### Historical Period Performance

| Period | Trades | Regime | Longs | L_WR | Shorts | S_WR | Net |
|--------|--------|--------|-------|------|--------|------|-----|
| 2008-2009 Bear | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2010-2015 Bull | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2016-2019 Bull | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2020-2021 Covid | 13 | BULL (89%) | 2 | 0% | 11 | 55% | $-1995 |
| 2022 Bear | 8 | BEAR (11%) | 1 | 0% | 7 | 86% | $749 |
| 2023-2025 Bull | 11 | BULL (89%) | 4 | 75% | 7 | 57% | $-249 |
| 2026 Selloff | 1 | BULL (100%) | 0 | 0% | 1 | 0% | $-498 |

**Direction**: excluded

## QQQ

**Bull Regime Longs** (trend_pullback): WR=70%, PF=1.33, n=23
**Bear Regime Shorts** (momentum_breakout): WR=100%, PF=inf, n=5

### Historical Period Performance

| Period | Trades | Regime | Longs | L_WR | Shorts | S_WR | Net |
|--------|--------|--------|-------|------|--------|------|-----|
| 2008-2009 Bear | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2010-2015 Bull | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2016-2019 Bull | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2020-2021 Covid | 19 | BULL (94%) | 7 | 100% | 12 | 50% | $749 |
| 2022 Bear | 16 | BEAR (7%) | 3 | 67% | 13 | 54% | $-742 |
| 2023-2025 Bull | 30 | BULL (91%) | 15 | 67% | 15 | 60% | $-250 |
| 2026 Selloff | 4 | BULL (91%) | 2 | 0% | 2 | 50% | $-1248 |

**Direction**: regime_adaptive_long_only

## IWM

**Bull Regime Longs** (momentum_breakout): WR=86%, PF=3.00, n=7
**Bear Regime Shorts** (momentum_breakout): WR=67%, PF=1.20, n=9

### Historical Period Performance

| Period | Trades | Regime | Longs | L_WR | Shorts | S_WR | Net |
|--------|--------|--------|-------|------|--------|------|-----|
| 2008-2009 Bear | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2010-2015 Bull | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2016-2019 Bull | 0 | — | 0 | 0% | 0 | 0% | $0 |
| 2020-2021 Covid | 12 | BULL (81%) | 3 | 100% | 9 | 67% | $998 |
| 2022 Bear | 5 | BEAR (2%) | 0 | 0% | 5 | 60% | $250 |
| 2023-2025 Bull | 15 | BULL (71%) | 6 | 100% | 9 | 67% | $1749 |
| 2026 Selloff | 1 | BULL (100%) | 1 | 0% | 0 | 0% | $-500 |

**Direction**: excluded
