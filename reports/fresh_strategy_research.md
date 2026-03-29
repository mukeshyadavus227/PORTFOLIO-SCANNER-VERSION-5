# Fresh Indicator Research — Swing Options Strategy

*588 signal/ticker/direction tests at 10-bar horizon*
*Data: 2020-01-01 to 2026-03-26, 15 tickers*

## Tier 1: Proven Predictors (WR>45%, PF>1.3, n>=20)

| Ticker | Signal | Dir | N | WR | PF | Avg Ret% | Sig/Mo | False% |
|--------|--------|-----|---|----|----|----------|--------|--------|
| NVDA | bb_touch_bounce | long | 37 | 70.3% | 5.78 | 5.38 | 0.5 | 83.8% |
| TSLA | donchian_breakout | long | 142 | 59.2% | 3.75 | 7.03 | 1.9 | 69.0% |
| TSLA | swing_breakout | long | 45 | 53.3% | 3.74 | 6.56 | 0.6 | 66.7% |
| TSLA | volume_price_spike | long | 68 | 60.3% | 3.59 | 6.80 | 0.9 | 79.4% |
| TSLA | bb_squeeze_expand | long | 178 | 60.1% | 3.49 | 6.38 | 2.4 | 71.9% |
| NVDA | swing_breakout | long | 57 | 52.6% | 2.95 | 3.98 | 0.8 | 78.9% |
| QQQ | keltner_breakout | long | 94 | 57.4% | 2.89 | 1.29 | 1.3 | 56.4% |
| TSLA | keltner_breakout | long | 59 | 49.2% | 2.71 | 5.50 | 0.8 | 72.9% |
| SLV | stoch_cross | long | 67 | 53.7% | 2.67 | 2.16 | 0.9 | 60.0% |
| XLE | volume_price_spike | long | 40 | 47.5% | 2.65 | 2.50 | 0.5 | 77.5% |
| NVDA | donchian_breakout | long | 173 | 56.6% | 2.65 | 3.50 | 2.3 | 79.8% |
| QQQ | bb_squeeze_expand | long | 257 | 59.9% | 2.62 | 1.30 | 3.4 | 60.3% |
| NVDA | keltner_breakout | long | 87 | 57.5% | 2.62 | 3.64 | 1.2 | 74.7% |
| SPY | macd_hist_flip | long | 71 | 57.7% | 2.61 | 0.91 | 0.9 | 45.1% |
| MSFT | ema21_pullback_bounce | long | 127 | 47.2% | 2.38 | 1.38 | 1.7 | 67.7% |
| GLD | swing_breakout | long | 55 | 49.1% | 2.32 | 1.07 | 0.7 | 52.7% |
| INTC | bb_touch_bounce | short | 52 | 57.7% | 2.31 | 2.64 | 0.7 | 76.9% |
| QQQ | ema21_pullback_bounce | long | 121 | 67.8% | 2.28 | 1.25 | 1.6 | 54.5% |
| QQQ | cci_momentum | long | 70 | 64.3% | 2.27 | 1.52 | 0.9 | 48.6% |
| SOFI | swing_breakout | short | 33 | 48.5% | 2.15 | 3.33 | 0.6 | 81.2% |
| SPY | keltner_breakout | long | 104 | 53.8% | 2.14 | 0.59 | 1.4 | 39.4% |
| NVDA | macd_hist_flip | long | 64 | 56.2% | 2.13 | 2.70 | 0.9 | 85.9% |
| XLE | swing_breakout | long | 52 | 50.0% | 2.13 | 1.52 | 0.7 | 68.6% |
| QQQ | macd_hist_flip | long | 62 | 56.5% | 2.11 | 1.03 | 0.8 | 51.6% |
| META | bb_squeeze_expand | long | 191 | 49.7% | 2.10 | 1.74 | 2.6 | 74.3% |
| AMZN | bb_squeeze_expand | long | 200 | 55.5% | 2.09 | 1.77 | 2.7 | 70.4% |
| GLD | cci_reversal | long | 58 | 48.3% | 2.08 | 0.85 | 0.8 | 39.7% |
| NVDA | bb_squeeze_expand | long | 170 | 60.0% | 2.08 | 2.62 | 2.3 | 82.4% |
| SOFI | keltner_breakout | long | 45 | 46.7% | 2.07 | 4.50 | 0.8 | 84.4% |
| SPY | bb_squeeze_expand | long | 261 | 54.4% | 2.06 | 0.66 | 3.5 | 44.8% |
| SOFI | donchian_breakout | long | 76 | 47.4% | 2.03 | 3.61 | 1.3 | 84.2% |
| NVDA | volume_price_spike | long | 68 | 50.0% | 2.02 | 2.32 | 0.9 | 85.3% |
| NVDA | stoch_cross | long | 66 | 59.1% | 2.01 | 3.01 | 0.9 | 80.0% |
| AMD | bb_touch_bounce | long | 48 | 47.9% | 2.00 | 2.19 | 0.6 | 81.2% |
| XLF | macd_hist_flip | long | 63 | 47.6% | 1.99 | 1.01 | 0.8 | 50.0% |
| GLD | macd_hist_flip | long | 62 | 45.2% | 1.98 | 0.88 | 0.8 | 46.8% |
| IWM | macd_hist_flip | long | 60 | 55.0% | 1.96 | 0.98 | 0.8 | 67.8% |
| MSFT | swing_breakout | long | 51 | 51.0% | 1.95 | 1.32 | 0.7 | 56.9% |
| SLV | volume_price_spike | long | 119 | 52.1% | 1.92 | 2.09 | 1.6 | 68.9% |
| GLD | bb_squeeze_expand | long | 212 | 48.6% | 1.89 | 0.81 | 2.8 | 47.6% |

## Tier 2: Marginal (WR>40%, PF>1.1)

| Ticker | Signal | Dir | N | WR | PF | Sig/Mo |
|--------|--------|-----|---|----|----|--------|
| SLV | rsi_oversold_exit | long | 18 | 77.8% | 10.67 | 0.2 |
| SPY | ema_cross_13_48 | long | 15 | 80.0% | 7.29 | 0.2 |
| AMZN | macd_zero_cross | long | 22 | 54.5% | 5.30 | 0.3 |
| SPY | macd_zero_cross | long | 19 | 52.6% | 5.23 | 0.2 |
| META | adx_trend_start | long | 17 | 64.7% | 4.73 | 0.2 |
| TSLA | rsi_oversold_exit | long | 18 | 61.1% | 4.58 | 0.2 |
| TSLA | adx_trend_start | long | 15 | 60.0% | 4.51 | 0.2 |
| AMZN | ema_cross_13_48 | long | 20 | 55.0% | 4.46 | 0.3 |
| GLD | adx_trend_start | long | 18 | 66.7% | 3.90 | 0.2 |
| TSLA | macd_zero_cross | long | 22 | 59.1% | 3.62 | 0.3 |
| AMZN | ema_cross_9_21 | long | 28 | 53.6% | 3.47 | 0.4 |
| TSLA | ema_cross_13_48 | long | 19 | 57.9% | 3.34 | 0.2 |
| NVDA | adx_trend_start | long | 20 | 55.0% | 2.99 | 0.3 |
| QQQ | adx_trend_start | long | 18 | 50.0% | 2.70 | 0.2 |
| MSFT | macd_zero_cross | long | 27 | 51.9% | 2.70 | 0.4 |
| GLD | bb_touch_bounce | long | 36 | 50.0% | 2.65 | 0.5 |
| TSLA | ema_cross_9_21 | long | 31 | 58.1% | 2.53 | 0.4 |
| MSFT | ema_cross_9_21 | long | 34 | 52.9% | 2.34 | 0.5 |
| META | supertrend_flip | long | 23 | 43.5% | 2.33 | 0.3 |
| TSLA | supertrend_flip | long | 20 | 50.0% | 2.26 | 0.3 |
| NVDA | supertrend_flip | long | 24 | 41.7% | 2.24 | 0.3 |
| XLE | ema_cross_13_48 | long | 24 | 54.2% | 2.16 | 0.3 |
| QQQ | macd_zero_cross | long | 22 | 54.5% | 2.16 | 0.3 |
| AMD | ema21_pullback_bounce | long | 98 | 44.9% | 2.10 | 1.3 |
| QQQ | supertrend_flip | long | 24 | 45.8% | 2.09 | 0.3 |
| SPY | ema_cross_9_21 | long | 24 | 50.0% | 2.08 | 0.3 |
| TSLA | macd_hist_flip | long | 60 | 45.0% | 2.02 | 0.8 |
| GLD | rsi_momentum_50 | long | 84 | 44.0% | 2.00 | 1.1 |
| NVDA | obv_trend | long | 727 | 52.3% | 1.98 | 9.7 |
| AMD | supertrend_flip | long | 23 | 60.9% | 1.92 | 0.3 |

## Ticker Clusters

| Ticker | Cluster | Hurst | ADX%>25 | AutoCorr1 | AvgATR% |
|--------|---------|-------|---------|-----------|---------|
| SPY | MEAN_REVERT | 0.531 | 38.0% | -0.155 | 1.44 |
| QQQ | MEAN_REVERT | 0.549 | 37.3% | -0.141 | 1.88 |
| IWM | MEAN_REVERT | 0.542 | 23.4% | -0.079 | 2.13 |
| SLV | MOMENTUM | 0.584 | 33.1% | 0.010 | 2.50 |
| GLD | TREND | 0.572 | 35.9% | 0.021 | 1.25 |
| XLE | MOMENTUM | 0.575 | 29.2% | -0.047 | 2.62 |
| XLF | MEAN_REVERT | 0.556 | 30.5% | -0.130 | 1.80 |
| NVDA | TREND | 0.555 | 42.6% | -0.098 | 4.16 |
| TSLA | TREND | 0.613 | 43.8% | -0.011 | 5.26 |
| AMD | TREND | 0.592 | 36.1% | -0.064 | 4.44 |
| MSFT | TREND | 0.558 | 43.0% | -0.151 | 2.29 |
| META | MEAN_REVERT | 0.530 | 43.2% | -0.051 | 3.25 |
| AMZN | MOMENTUM | 0.540 | 33.3% | -0.031 | 2.89 |
| SOFI | MOMENTUM | 0.541 | 28.7% | 0.046 | 6.02 |
| INTC | TREND | 0.566 | 38.1% | -0.088 | 3.62 |

**MEAN_REVERT:** SPY, QQQ, IWM, XLF, META
**MOMENTUM:** SLV, XLE, AMZN, SOFI
**TREND:** GLD, NVDA, TSLA, AMD, MSFT, INTC

## Strategy Archetypes

### Archetype 1: Trend Pullback
- **For:** TREND cluster tickers
- **Entry:** Price pulls back to EMA(21), bounces above with EMA9 > EMA21
- **Confirmation:** RSI > 50, MACD histogram positive
- **Stop:** Below recent swing low or 2x ATR
- **Target:** 2x ATR from entry or previous swing high

### Archetype 2: Momentum Breakout
- **For:** MOMENTUM cluster tickers
- **Entry:** Close breaks above Donchian(20) high with volume > 1.5x SMA
- **Confirmation:** ADX rising, SuperTrend bullish
- **Stop:** Below Donchian midpoint or 2x ATR
- **Target:** 2x ATR or next resistance level

### Archetype 3: Mean Reversion
- **For:** MEAN_REVERT cluster tickers
- **Entry:** RSI exits oversold (<30 crosses above) + BB lower band touch
- **Confirmation:** Stochastic cross up, volume expansion
- **Stop:** Below recent swing low
- **Target:** BB midline (mean) or 1.5x ATR
