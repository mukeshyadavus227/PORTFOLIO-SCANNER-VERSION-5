# Per-Ticker Backtest Results (Walk-Forward)

*48 param combos × 3 archetypes × 2 directions, 3 walk-forward windows*

| Ticker | Direction | L_Arch | L_WR | L_PF | L_N | S_Arch | S_WR | S_PF | S_N |
|--------|-----------|--------|------|------|-----|--------|------|------|-----|
| SPY | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |
| QQQ | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |
| IWM | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |
| SLV | long_only | momentum | 81% | 2.17 | 32 | — | 0% | 0.00 | 0 |
| GLD | long_only | trend_pu | 87% | 3.25 | 15 | — | 0% | 0.00 | 0 |
| XLE | long_only | momentum | 80% | 2.00 | 10 | — | 0% | 0.00 | 0 |
| XLF | long_only | mean_rev | 75% | 1.50 | 20 | — | 0% | 0.00 | 0 |
| NVDA | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |
| TSLA | long_only | trend_pu | 77% | 3.32 | 13 | — | 0% | 0.00 | 0 |
| AMD | both | trend_pu | 80% | 2.00 | 15 | trend_pu | 69% | 1.38 | 42 |
| MSFT | both | trend_pu | 79% | 2.75 | 14 | trend_pu | 67% | 1.24 | 39 |
| META | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |
| AMZN | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |
| SOFI | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |
| INTC | excluded | — | 0% | 0.00 | 0 | — | 0% | 0.00 | 0 |

## Optimal Parameters Per Ticker

### SLV (long_only)
- Long (momentum_breakout): stop=3.0x ATR, target=1.5x ATR, hold=20 bars, cooldown=2% | OOS WR=81% PF=2.17

### GLD (long_only)
- Long (trend_pullback): stop=3.0x ATR, target=1.5x ATR, hold=20 bars, cooldown=2% | OOS WR=87% PF=3.25

### XLE (long_only)
- Long (momentum_breakout): stop=2.0x ATR, target=1.5x ATR, hold=15 bars, cooldown=2% | OOS WR=80% PF=2.00

### XLF (long_only)
- Long (mean_reversion): stop=1.5x ATR, target=2.0x ATR, hold=20 bars, cooldown=2% | OOS WR=75% PF=1.50

### TSLA (long_only)
- Long (trend_pullback): stop=3.0x ATR, target=2.0x ATR, hold=20 bars, cooldown=2% | OOS WR=77% PF=3.32

### AMD (both)
- Long (trend_pullback): stop=3.0x ATR, target=1.5x ATR, hold=15 bars, cooldown=2% | OOS WR=80% PF=2.00
- Short (trend_pullback): stop=3.0x ATR, target=1.5x ATR, hold=20 bars | OOS WR=69% PF=1.38

### MSFT (both)
- Long (trend_pullback): stop=3.0x ATR, target=2.0x ATR, hold=20 bars, cooldown=2% | OOS WR=79% PF=2.75
- Short (trend_pullback): stop=3.0x ATR, target=1.5x ATR, hold=20 bars | OOS WR=67% PF=1.24
