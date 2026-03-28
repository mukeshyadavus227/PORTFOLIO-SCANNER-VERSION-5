# Portfolio Scanner V5

Adaptive multi-strategy TradingView indicator with webhook alerting for automated signal aggregation.

## What It Does

A Pine Script v6 indicator that runs on each symbol in a TradingView watchlist. It classifies the market regime, evaluates 4 independent sub-strategies, scores them, selects a winner, and fires a webhook alert with a JSON payload when conviction exceeds a configurable threshold.

The webhook payload is designed for a downstream signal aggregator that collects signals from all symbols, ranks them cross-sectionally, and executes the top picks.

## Architecture

All logic lives in a single file: `src/portfolio_scanner_v5.pine`

**Regime Detection** — 3-axis classification using ADX (trend strength), Choppiness Index (trending vs. choppy), and Bollinger Band Width (volatility expansion/contraction). Produces 5 regimes: `TRENDING`, `BREAKOUT`, `MOMENTUM`, `MEAN_REVERT`, `NEUTRAL`.

**Sub-Strategies:**

| ID | Name | Logic |
|----|------|-------|
| S1 | RSI Mean Reversion | Oversold bounce in confirmed uptrend (price > 200 SMA) |
| S2 | Donchian Breakout | Channel breakout + ADX confirmation + volume spike |
| S3 | EMA/VWAP Momentum | EMA crossover + VWAP alignment + MACD confirmation |
| S4 | Multi-TF Trend | Weekly trend alignment + daily pullback entry |

**Winner Selection** — Scores each sub-strategy based on regime alignment, signal strength, and confirmation factors. The highest-scoring strategy generates the trade signal.

**Webhook Output** — JSON payload includes: ticker, direction, strategy name, conviction score, regime, entry/SL/TP levels, cross-sectional features (relative volume, ATR percentile, distance from 52-week high/low, rate of change, sector tag, beta).

## Deployment

1. Copy `src/portfolio_scanner_v5.pine` into TradingView's Pine Script Editor
2. Add the indicator to each chart in your watchlist
3. Create an alert per symbol:
   - **Condition:** "Any alert() function call"
   - **Webhook URL:** Your aggregator endpoint
   - **Message:** `{{alert.message}}`

## Key Configuration Inputs

| Input | Default | Description |
|-------|---------|-------------|
| Min Conviction Score | 75 | Minimum score to fire a signal (60=loose, 75=production, 85=strict) |
| Enable Short Signals | false | Allow short-side signals |
| Enforce Regime-Strategy Alignment | true | Only fire when strategy matches current regime |
| Cooldown Bars After Signal | 15 | Prevent duplicate signals within N bars |
| Webhook Token | *(change this)* | Authentication token sent in webhook payload |
| Sector Tag | TECH | Must be set per symbol to match your universe config |
| Asset Class | STK | ETF or STK |
| Beta to SPY | 1.0 | Approximate beta, used for portfolio beta targeting |

Each sub-strategy and regime detection module has additional tunable parameters accessible in TradingView's indicator settings panel.

## License

Proprietary. All rights reserved.
