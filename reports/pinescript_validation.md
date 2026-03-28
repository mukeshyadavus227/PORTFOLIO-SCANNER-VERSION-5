# Pine Script V6 Validation Report

## Expected Values for TradingView Comparison

TradingView backtest results should be within 10-15% of these numbers.
Larger divergences indicate a calculation bug.

| Ticker | Trades | WR% | PF | Net PnL | Sharpe | Avg Bars |
|--------|--------|-----|-----|---------|--------|----------|
| SPY | 58 | 41.4 | 1.31 | $675.67 | 0.51 | 10.6 |
| INTC | 89 | 42.7 | 1.4 | $4405.96 | 0.59 | 11.6 |
| AMD | 59 | 42.4 | 1.34 | $4028.23 | 0.61 | 9.9 |
| AMZN | 77 | 41.6 | 1.14 | $1185.61 | 0.25 | 9.9 |
| QQQ | 39 | 46.2 | 1.37 | $757.72 | 0.63 | 8.7 |

**Combined:** 322 trades, $11053.19 net PnL

## Per-Ticker Trade Details

### SPY

- Mode A (Trend): 58 trades
- Mode B (Breakout): 0 trades
- Exit breakdown: {'regime_change': 37, 'time_stop': 11, 'stop_loss': 8, 'take_profit': 2}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2024-08-23 | 2024-08-23 | A | 80 | $17.72 | 0 | regime_change |
| 2024-10-16 | 2024-10-29 | A | 95 | $12.84 | 9 | regime_change |
| 2024-11-14 | 2024-11-14 | A | 95 | $-34.84 | 0 | regime_change |
| 2025-07-14 | 2025-08-01 | A | 90 | $-14.68 | 14 | regime_change |
| 2025-08-11 | 2025-08-21 | A | 85 | $-16.51 | 8 | regime_change |

### INTC

- Mode A (Trend): 83 trades
- Mode B (Breakout): 6 trades
- Exit breakdown: {'stop_loss': 21, 'take_profit': 16, 'regime_change': 31, 'time_stop': 21}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2023-11-28 | 2023-12-27 | A | 85 | $801.84 | 20 | time_stop |
| 2025-08-18 | 2025-09-16 | B | 80 | $259.08 | 20 | time_stop |
| 2025-10-02 | 2025-10-30 | A | 90 | $607.21 | 20 | time_stop |
| 2025-12-03 | 2025-12-10 | A | 95 | $-303.72 | 5 | regime_change |
| 2026-01-12 | 2026-01-26 | B | 95 | $-201.24 | 9 | regime_change |

### AMD

- Mode A (Trend): 44 trades
- Mode B (Breakout): 15 trades
- Exit breakdown: {'regime_change': 23, 'stop_loss': 13, 'take_profit': 10, 'time_stop': 13}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2024-01-10 | 2024-01-19 | A | 95 | $793.95 | 6 | take_profit |
| 2024-02-23 | 2024-03-19 | A | 90 | $-15.15 | 17 | stop_loss |
| 2025-07-14 | 2025-07-28 | A | 80 | $968.04 | 10 | take_profit |
| 2025-08-14 | 2025-08-20 | A | 95 | $-402.87 | 4 | stop_loss |
| 2025-10-27 | 2025-11-07 | A | 85 | $-467.93 | 9 | stop_loss |

### AMZN

- Mode A (Trend): 69 trades
- Mode B (Breakout): 8 trades
- Exit breakdown: {'take_profit': 11, 'stop_loss': 14, 'regime_change': 34, 'time_stop': 18}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2024-03-27 | 2024-04-18 | A | 75 | $-21.09 | 15 | stop_loss |
| 2024-07-08 | 2024-07-16 | A | 90 | $-171.72 | 6 | stop_loss |
| 2024-12-09 | 2024-12-27 | A | 85 | $-78.02 | 13 | regime_change |
| 2025-07-08 | 2025-07-08 | A | 90 | $-102.44 | 0 | regime_change |
| 2025-07-25 | 2025-08-01 | A | 90 | $-368.40 | 5 | regime_change |

### QQQ

- Mode A (Trend): 39 trades
- Mode B (Breakout): 0 trades
- Exit breakdown: {'regime_change': 28, 'take_profit': 5, 'time_stop': 6}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2024-02-23 | 2024-02-28 | A | 90 | $-51.29 | 3 | regime_change |
| 2024-06-21 | 2024-07-17 | A | 90 | $2.70 | 17 | regime_change |
| 2024-12-18 | 2024-12-18 | A | 95 | $-171.21 | 0 | regime_change |
| 2025-07-14 | 2025-08-05 | A | 85 | $53.34 | 16 | regime_change |
| 2025-08-13 | 2025-08-20 | A | 90 | $-137.96 | 5 | regime_change |

## Repainting Risk Analysis

- **PASS**: All 5 request.security calls use barmerge.lookahead_off (5 instances)
- **PASS**: process_orders_on_close=true — orders processed on bar close, filled at next bar open
- **PASS**: barstate.isconfirmed gate present — signals only fire on confirmed (closed) bars
- **PASS**: No forward-looking index references found
- **PASS**: calc_on_every_tick=false — no intra-bar recalculation

## JSON Payload Validation

- PASS: Mode A Entry payload — valid JSON (26 fields)
-   All required fields present
- PASS: Mode B Breakout payload — valid JSON (26 fields)
-   All required fields present
- PASS: Exit payload — valid JSON (14 fields)
-   All required fields present

### Sample Payloads

**Mode A Entry:**
```json
{
  "token": "mukesh-tv-2026",
  "ticker": "SPY",
  "action": "LONG_ENTRY",
  "mode": "trend_continuation",
  "conviction": 85.0,
  "regime": "trending_up",
  "entry_price": 580.25,
  "stop_level": 575.1,
  "atr": 8.5,
  "atr_pct": 1.47,
  "rsi": 62.5,
  "adx": 32.1,
  "di_plus": 28.5,
  "di_minus": 15.2,
  "pct_from_high": 0.85,
  "macd_hist": 1.25,
  "suggested_hold_days": 10,
  "weekly_trend": "bullish",
  "cluster": "Trend",
  "options_guidance": "directional_long",
  "exit_reason": "",
  "bb_upper": 595.5,
  "bb_lower": 565.0,
  "bb_width": 5.3,
  "timeframe": "1D",
  "bar_time": 1711584000000
}
```

**Mode B Breakout:**
```json
{
  "token": "mukesh-tv-2026",
  "ticker": "SPY",
  "action": "LONG_ENTRY",
  "mode": "breakout",
  "conviction": 70.0,
  "regime": "volatile_breakout",
  "entry_price": 580.25,
  "stop_level": 575.1,
  "atr": 8.5,
  "atr_pct": 1.47,
  "rsi": 62.5,
  "adx": 32.1,
  "di_plus": 28.5,
  "di_minus": 15.2,
  "pct_from_high": 0.85,
  "macd_hist": 1.25,
  "suggested_hold_days": 10,
  "weekly_trend": "bullish",
  "cluster": "Momentum",
  "options_guidance": "breakout_long",
  "exit_reason": "",
  "bb_upper": 595.5,
  "bb_lower": 565.0,
  "bb_width": 5.3,
  "timeframe": "1D",
  "bar_time": 1711584000000
}
```

**Exit:**
```json
{
  "token": "mukesh-tv-2026",
  "ticker": "SPY",
  "action": "EXIT",
  "mode": "exit",
  "conviction": 0,
  "regime": "trending_up",
  "entry_price": 0,
  "stop_level": 0,
  "atr": 8.5,
  "rsi": 82.3,
  "adx": 28.5,
  "exit_reason": "take_profit",
  "bars_in_trade": 12,
  "bar_time": 1712448000000
}
```

## Potential Divergence Notes

Expected sources of 5-15% divergence between Python and TradingView:

1. **Weekly EMA seeding**: TV calculates weekly EMAs from the full weekly
   history which may differ from our daily-resampled approximation
2. **Bar alignment**: TV weekly bars may align to Sunday or Monday
   vs our Friday-anchored resample
3. **Slippage model**: TV applies slippage differently (fixed tick vs %)
4. **Position sizing**: TV uses equity curve for 10% sizing which
   compounds differently than our fixed initial capital approach
5. **ADX/RSI seed period**: Minor differences in initial SMA seed
   window can propagate for ~50 bars before converging
