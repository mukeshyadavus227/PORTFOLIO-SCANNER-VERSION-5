# Hybrid Timeframe Analysis

*Daily qualification + simulated PM-session intraday timing*

## Methodology
- Daily signal qualification: same archetype conditions as V1
- Hybrid entry: reduced slippage proxy for PM session entry (closer to close)
- Comparison: pure daily entry vs hybrid timing
- Note: Real 4h/6h data not available; daily proxy used

## Results

| Ticker | Arch | Daily N | Daily WR | Daily PF | Hybrid N | Hybrid WR | Hybrid PF | Delta |
|--------|------|---------|----------|----------|----------|-----------|-----------|-------|
| SPY | mean_rev | 109 | 24.8 | 0.17 | 109 | 24.8 | 0.17 | +0.0 |
| QQQ | mean_rev | 99 | 28.3 | 0.20 | 99 | 28.3 | 0.20 | +0.0 |
| IWM | mean_rev | 87 | 37.9 | 0.32 | 87 | 37.9 | 0.32 | +0.0 |
| SLV | momentum | 58 | 55.2 | 0.65 | 58 | 55.2 | 0.65 | +0.0 |
| GLD | trend_pu | 71 | 38.0 | 0.33 | 71 | 38.0 | 0.33 | +0.0 |
| XLE | momentum | 33 | 51.5 | 0.55 | 33 | 51.5 | 0.55 | +0.0 |
| TSLA | trend_pu | 71 | 49.3 | 0.53 | 71 | 49.3 | 0.53 | +0.0 |
| AMD | trend_pu | 78 | 44.9 | 0.43 | 78 | 44.9 | 0.43 | +0.0 |
| MSFT | trend_pu | 74 | 50.0 | 0.56 | 74 | 50.0 | 0.56 | +0.0 |
| NVDA | trend_pu | 67 | 32.8 | 0.27 | 67 | 32.8 | 0.27 | +0.0 |
| AMZN | momentum | 45 | 37.8 | 0.32 | 45 | 37.8 | 0.32 | +0.0 |

## Conclusion
Hybrid timing produces similar results to pure daily entry.
The intraday timing layer is an execution optimization for bot deployment.

## Pine Script V2 Architecture
```
Layer 1 — WEEKLY (request.security W): Regime detection
Layer 2 — DAILY  (request.security D): Signal QUALIFICATION
Layer 3 — INTRADAY (native 4h/6h):     Entry TIMING + session filter
```

## Paper Trading Notes
- Intraday timing layer is APPROXIMATE — needs validation with live 4h/6h data
- Session filter: signals fire only when hour >= 12 ET (PM session)
- Expect to fine-tune intraday EMA/RSI parameters during first 2 weeks
- maxHoldBars on 4h chart: 40 bars ≈ 10 trading days (same theta window)