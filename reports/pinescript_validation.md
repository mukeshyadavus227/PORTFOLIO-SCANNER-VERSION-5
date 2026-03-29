# Pine Script V6 Validation Report

## Expected Values for TradingView Comparison

TradingView backtest results should be within 10-15% of these numbers.
Larger divergences indicate a calculation bug.

| Ticker | Trades | WR% | PF | Net PnL | Sharpe | Avg Bars |
|--------|--------|-----|-----|---------|--------|----------|
| SPY | 29 | 51.7 | 1.6 | $696.08 | 0.89 | 10.1 |
| INTC | 60 | 53.3 | 1.93 | $5495.05 | 1.08 | 10.2 |
| AMD | 50 | 58.0 | 1.8 | $6069.77 | 1.21 | 9.6 |
| AMZN | 49 | 40.8 | 0.96 | $-213.31 | -0.07 | 9.2 |
| QQQ | 20 | 50.0 | 1.76 | $628.01 | 1.21 | 9.4 |

**Combined:** 208 trades, $12675.60 net PnL

## Per-Ticker Trade Details

### SPY

- Mode A (Trend): 28 trades
- Mode B (Breakout): 1 trades
- Exit breakdown: {'take_profit': 4, 'time_stop': 6, 'regime_change': 19}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2023-07-31 | 2023-08-09 | A | 95 | $-119.70 | 7 | regime_change |
| 2023-11-29 | 2023-12-28 | A | 85 | $192.30 | 20 | time_stop |
| 2024-01-09 | 2024-01-17 | A | 90 | $1.10 | 5 | regime_change |
| 2024-01-26 | 2024-02-20 | A | 85 | $88.60 | 16 | regime_change |
| 2024-07-03 | 2024-07-10 | A | 90 | $110.67 | 4 | take_profit |

### INTC

- Mode A (Trend): 55 trades
- Mode B (Breakout): 5 trades
- Exit breakdown: {'take_profit': 17, 'regime_change': 33, 'time_stop': 10}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2021-02-25 | 2021-03-09 | A | 95 | $17.00 | 8 | regime_change |
| 2021-04-12 | 2021-04-20 | A | 95 | $-405.23 | 6 | regime_change |
| 2023-11-20 | 2023-12-19 | A | 90 | $324.18 | 20 | time_stop |
| 2025-10-02 | 2025-10-30 | A | 90 | $607.21 | 20 | time_stop |
| 2026-01-14 | 2026-01-26 | B | 100 | $-660.90 | 7 | regime_change |

### AMD

- Mode A (Trend): 30 trades
- Mode B (Breakout): 20 trades
- Exit breakdown: {'regime_change': 26, 'take_profit': 15, 'time_stop': 9}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2021-10-26 | 2021-11-04 | A | 90 | $577.00 | 7 | take_profit |
| 2021-11-30 | 2021-12-06 | A | 85 | $-729.90 | 4 | regime_change |
| 2023-12-12 | 2024-01-11 | A | 90 | $580.12 | 20 | time_stop |
| 2025-06-25 | 2025-07-24 | B | 100 | $737.95 | 20 | time_stop |
| 2025-10-16 | 2025-11-07 | A | 90 | $-60.33 | 16 | regime_change |

### AMZN

- Mode A (Trend): 44 trades
- Mode B (Breakout): 5 trades
- Exit breakdown: {'take_profit': 9, 'regime_change': 30, 'time_stop': 10}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2020-08-19 | 2020-09-04 | A | 95 | $-15.88 | 12 | regime_change |
| 2023-06-02 | 2023-07-03 | A | 85 | $208.60 | 20 | time_stop |
| 2024-02-12 | 2024-02-16 | A | 90 | $-151.40 | 4 | regime_change |
| 2024-04-10 | 2024-04-17 | A | 100 | $-43.50 | 5 | regime_change |
| 2024-12-12 | 2024-12-23 | A | 85 | $-98.34 | 7 | regime_change |

### QQQ

- Mode A (Trend): 20 trades
- Mode B (Breakout): 0 trades
- Exit breakdown: {'regime_change': 12, 'take_profit': 5, 'time_stop': 3}

| Entry | Exit | Mode | Score | PnL | Bars | Exit Reason |
|-------|------|------|-------|-----|------|-------------|
| 2023-06-02 | 2023-07-03 | A | 85 | $227.72 | 20 | time_stop |
| 2023-07-13 | 2023-08-03 | A | 95 | $-32.51 | 15 | regime_change |
| 2023-11-24 | 2023-12-22 | A | 95 | $221.64 | 20 | time_stop |
| 2024-01-26 | 2024-02-16 | A | 85 | $64.32 | 15 | regime_change |
| 2024-07-03 | 2024-07-17 | A | 80 | $-47.60 | 9 | regime_change |

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
