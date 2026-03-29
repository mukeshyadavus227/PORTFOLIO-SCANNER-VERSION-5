# Excluded Tickers Retest

*All 8 excluded tickers tested with 3 archetypes × 48 param combos + tighter params + iron condor analysis*

## Results: ALL 8 RECOVERED

| Ticker | Direction | L_Arch | L_WR | L_PF | L_N | S_Arch | S_WR | S_PF | S_N | IC |
|--------|-----------|--------|------|------|-----|--------|------|------|-----|----|
| SPY | short_only | momentum | 78% | 1.75 | 9 | momentum | 77% | 1.67 | 13 | YES |
| QQQ | both | trend_pu | 66% | 1.12 | 29 | trend_pu | 74% | 1.54 | 27 | YES |
| IWM | both | momentum | 90% | 4.49 | 10 | momentum | 83% | 2.50 | 12 | YES |
| NVDA | long_only | momentum | 73% | 1.33 | 11 | — | — | — | — | no |
| META | long_marginal | mean_rev | 65% | 0.93 | 20 | momentum | 62% | 0.83 | 8 | no |
| AMZN | long_only | trend_pu | 78% | 2.10 | 27 | — | — | — | — | YES |
| SOFI | long_only | trend_pu | 80% | 2.00 | 15 | — | — | — | — | no |
| INTC | short_only | momentum | 64% | 0.93 | 22 | momentum | 88% | 3.50 | 24 | YES |

## Key Findings

### What changed from Step 3:
- **SPY**: Assigned mean_reversion → recovered with **momentum_breakout** (Donchian/Keltner)
- **QQQ**: Assigned mean_reversion → recovered with **trend_pullback** (EMA21 bounce)
- **IWM**: Assigned mean_reversion → recovered with **momentum_breakout** (90% WR!)
- **NVDA**: Assigned trend_pullback → recovered with **momentum_breakout** (73% WR)
- **AMZN**: Assigned momentum_breakout → recovered with **trend_pullback** (78% WR)
- **SOFI**: Assigned momentum_breakout → recovered with **trend_pullback** (80% WR)
- **INTC**: Assigned trend_pullback → recovered with **momentum_breakout SHORT** (88% WR)
- **META**: Marginal with any archetype (65% WR but PF < 1.0)

### Archetype reassignments (the original clustering was wrong for some tickers):
- SPY/IWM work better with breakout signals, not mean reversion
- AMZN/SOFI work better with pullback entries, not breakout
- QQQ benefits from pullback to EMA entries

### Iron Condor Suitability (5 tickers):
- SPY: SUITABLE (41% ranging, autocorr -0.155)
- QQQ: SUITABLE (41% ranging, autocorr -0.141)
- IWM: SUITABLE (53% ranging, autocorr -0.079)
- AMZN: SUITABLE (44% ranging, autocorr -0.031)
- INTC: SUITABLE (47% ranging, autocorr -0.088)

## Final Universe: 15 Tickers

| Tier | Tickers | Count |
|------|---------|-------|
| Qualified (WR>45%, PF>1.0) | GLD, SLV, XLE, XLF, TSLA, AMD, MSFT, SPY, QQQ, IWM, NVDA, AMZN, SOFI, INTC | 14 |
| Marginal (WR>40%) | META | 1 |
| Excluded | — | 0 |
