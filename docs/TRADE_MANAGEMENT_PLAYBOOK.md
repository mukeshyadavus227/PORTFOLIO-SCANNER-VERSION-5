# Trade Management Playbook — Model C Managed Spreads

*For the automated trading bot (Claude brain) receiving webhook alerts from Swing Options V2*

## Trade Structure: Vertical Debit Spreads

All directional trades use **vertical debit spreads** (call spreads for LONG, put spreads for SHORT).
This provides defined risk, defined reward, and better payoff ratio than naked options.

---

## ON ENTRY SIGNAL (webhook action = "LONG" or "SHORT")

### Step 1: Determine Spread Parameters
- **Direction**: LONG → buy call vertical spread. SHORT → buy put vertical spread.
- **Width**: $5.00 for stocks above $100 (MSFT, TSLA, AMD, NVDA, META, AMZN, GLD). $2.50 for stocks below $100 (SLV, XLE, SOFI, XLF, IWM).
- **DTE**: 45-60 days to expiration.
- **Long leg delta**: 0.45-0.55 (at-the-money).
- **Short leg**: $5 or $2.50 further OTM.

### Step 2: Position Sizing
| Tier | Tickers | Max Risk Per Trade | Position Size |
|------|---------|-------------------|---------------|
| **TIER 1** | SLV, MSFT, TSLA, XLE | 3% of account | Full |
| **TIER 2** | AMD, SOFI, GLD | 1.5% of account | Half |
| **TIER 3** | All others | 0% (paper only) | Do not trade live |

- **Max simultaneous positions**: 7 (Tier 1 gets priority)
- **Max total account risk**: 20% across all positions
- **Example**: $50K account → max $1,500/trade (Tier 1) or $750/trade (Tier 2)

### Step 3: Execute
- Enter the spread at mid-price or slightly above
- Set a limit order; do not chase with market orders
- If not filled within 30 minutes, adjust limit by $0.05

---

## ACTIVE MANAGEMENT (check every 4h/6h bar)

### Rule 1: Take Profit at 50%
```
IF spread_value >= 1.5 × entry_cost THEN CLOSE
```
- The spread gained 50% of max profit → lock it in
- Don't wait for full max profit (theta and IV work against you)

### Rule 2: Cut Loss at 50%
```
IF spread_value <= 0.5 × entry_cost THEN CLOSE
```
- The spread lost 50% of value → cut the loss
- Do NOT hold to full loss hoping for recovery

### Rule 3: Time Exit at Day 15
```
IF days_since_entry >= 15 THEN CLOSE
```
- Theta accelerates after 21 DTE
- Entry at 45-60 DTE minus 15 days = exiting at 30-45 DTE (before theta cliff)
- Close regardless of profit or loss

### Rule 4: Signal Exit
```
IF webhook action = "EXIT" THEN CLOSE
```
- The Pine Script detected a technical exit (EMA stop, RSI reversal, etc.)
- Close immediately at market

### Priority Order (first rule triggered wins):
1. Signal Exit (immediate)
2. Take Profit (check every bar)
3. Cut Loss (check every bar)
4. Time Exit (check daily)

---

## ON IRON CONDOR SIGNAL (webhook action = "IRON_CONDOR")

### Eligible Tickers: SPY, QQQ, IWM, AMZN, INTC

### Structure
- Sell iron condor: short call + short put at 1 standard deviation
- Buy wings: $5-$10 further out for defined risk
- DTE: 30-45 days
- Target credit: 30-35% of wing width

### Management
- **Take profit**: Close at 50% of credit received
- **Stop loss**: Close at 2× credit received (loss = 1× credit)
- **Time exit**: Close at 14 DTE regardless
- **Max 2 iron condors simultaneously**

### Position Sizing
- Same tier-based sizing as directional trades
- Iron condors are ONLY for Tier 3 tickers (not live-trading directional on these)

---

## RISK MANAGEMENT RULES

### Daily Limits
- Max 2 new positions per day
- No new positions if account is down >5% for the week

### Correlation Control
- Max 3 positions in the same sector (tech: MSFT, AMD, TSLA, NVDA, META)
- SPY/QQQ/IWM count as correlated — max 1 directional + 1 iron condor

### Earnings Blackout
- No new positions within 5 trading days of earnings
- Close existing positions 2 days before earnings if profitable

### IV Spike Filter
- Do not enter spreads when IV rank > 80% (options too expensive)
- Exception: iron condors benefit from high IV — these are OK

---

## EXPECTED PERFORMANCE (Model C Backtest, 2020-2026)

| Metric | Tier 1 | Tier 2 | Combined |
|--------|--------|--------|----------|
| Tickers | SLV, MSFT, TSLA, XLE | AMD, SOFI, GLD | 7 |
| Avg Win Rate | 51.5% | 41% | 47% |
| Profit Factor | 1.15 | 0.74 | 0.97 |
| Net PnL (backtest) | +$3,747 | -$6,745 | -$2,998 |
| Expected per trade | +$14 | -$27 | -$3 |

**Note**: Tier 1 alone is profitable. Tier 2 should be paper-traded until validation.

### Monthly P&L Estimate ($50K Account, Tier 1 Only)
- Trades per month: ~8-12 across 4 Tier 1 tickers
- Avg risk per trade: $1,500 (3% of $50K)
- Expected win: +$750 (50% of $1,500)
- Expected loss: -$750 (50% of $1,500)
- At 51.5% WR with 10 trades/mo: ~$150-300/month profit
- Monthly return: ~0.3-0.6% of account
- Annualized: ~4-7% (conservative, before commissions)

**This is a conservative, income-generating strategy — not a get-rich-quick system.**
