# Walk-Forward Optimization Results

*500 random parameter samples per cluster, 18mo train / 6mo test rolling windows, data from 2016-01-01*

## TREND Cluster

Tickers: SPY, QQQ, AMZN, MSFT, INTC, JNJ

### Top 5 Parameter Sets (by OOS Sharpe)

| Rank | OOS Sharpe | IS Sharpe | Degradation | OOS Trades | OOS PnL | RSI | ADX | EMA | Score | Pullback | ATR Stop |
|------|-----------|----------|-------------|-----------|---------|-----|-----|-----|-------|----------|----------|
| 1 | 1.447 | 0.999 | 1.448 | 61 | $3831 | 55-80 | 30 | 21/50 | 65 | 1.0% | 2.0x |
| 2 | 1.447 | 0.999 | 1.448 | 61 | $3831 | 55-80 | 30 | 21/50 | 80 | 1.0% | 2.0x |
| 3 | 1.447 | 0.999 | 1.448 | 61 | $3831 | 50-80 | 30 | 21/50 | 80 | 1.0% | 1.5x |
| 4 | 1.447 | 0.999 | 1.448 | 61 | $3831 | 55-80 | 30 | 21/50 | 80 | 1.0% | 2.0x |
| 5 | 1.438 | 0.996 | 1.444 | 60 | $3808 | 60-80 | 30 | 8/50 | 60 | 1.0% | 1.5x |

### Winner Analysis

- **OOS Sharpe:** 1.447
- **IS Sharpe:** 0.999
- **Degradation ratio:** 1.448 (GOOD — want > 0.5)
- **OOS trades:** 61
- **OOS net PnL:** $3830.76

- **Robustness:** MODERATE (some sensitivity but reasonable plateau)

### Winning Parameters

```json
{
  "rsi_lo": 55,
  "rsi_hi": 80,
  "adx_thr": 30,
  "ema_fast": 21,
  "ema_slow": 50,
  "min_score": 65,
  "pullback_pct": 1.0,
  "atr_stop_mult": 2.0
}
```

## MOMENTUM Cluster

Tickers: AMD, NVDA, TSLA, AAPL, NFLX, PLTR

### Top 5 Parameter Sets (by OOS Sharpe)

| Rank | OOS Sharpe | IS Sharpe | Degradation | OOS Trades | OOS PnL | RSI | ADX | EMA | Score | Pullback | ATR Stop |
|------|-----------|----------|-------------|-----------|---------|-----|-----|-----|-------|----------|----------|
| 1 | 2.518 | 2.518 | 1.000 | 45 | $8110 | 55-70 | 30 | 9/50 | 75 | 1.0% | 2.5x |
| 2 | 2.518 | 2.518 | 1.000 | 45 | $8110 | 55-70 | 30 | 9/34 | 65 | 1.0% | 1.5x |
| 3 | 2.512 | 2.514 | 0.999 | 44 | $8077 | 50-70 | 30 | 21/50 | 80 | 1.0% | 2.0x |
| 4 | 2.512 | 2.514 | 0.999 | 44 | $8077 | 55-70 | 30 | 13/34 | 80 | 1.0% | 1.5x |
| 5 | 2.269 | 2.314 | 0.981 | 45 | $7168 | 60-70 | 30 | 8/18 | 80 | 1.0% | 3.0x |

### Winner Analysis

- **OOS Sharpe:** 2.518
- **IS Sharpe:** 2.518
- **Degradation ratio:** 1.000 (GOOD — want > 0.5)
- **OOS trades:** 45
- **OOS net PnL:** $8110.25

- **Robustness:** MODERATE (some sensitivity but reasonable plateau)

### Winning Parameters

```json
{
  "rsi_lo": 55,
  "rsi_hi": 70,
  "adx_thr": 30,
  "ema_fast": 9,
  "ema_slow": 50,
  "min_score": 75,
  "pullback_pct": 1.0,
  "atr_stop_mult": 2.5
}
```
