"""
Trade simulation engine for Portfolio Scanner V5.

Takes composite signals from the scorer and simulates trades with realistic
execution, ATR-based stops/targets, and daily risk management limits.
"""

from dataclasses import dataclass, field
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ═══════════════════════════════════════════════════════════════════════════
# Instrument presets
# ═══════════════════════════════════════════════════════════════════════════

INSTRUMENT_PRESETS: dict[str, dict] = {
    "MNQ":  dict(point_value=2.0,    tick_size=0.25, commission_per_contract=1.50,  slippage_ticks=2),
    "MES":  dict(point_value=5.0,    tick_size=0.25, commission_per_contract=1.50,  slippage_ticks=2),
    "SPY":  dict(point_value=1.0,    tick_size=0.01, commission_per_contract=0.005, slippage_ticks=1),
    "QQQ":  dict(point_value=1.0,    tick_size=0.01, commission_per_contract=0.005, slippage_ticks=1),
    "CL":   dict(point_value=1000.0, tick_size=0.01, commission_per_contract=2.50,  slippage_ticks=2),
    "GLD":  dict(point_value=1.0,    tick_size=0.01, commission_per_contract=0.005, slippage_ticks=1),
}


# ═══════════════════════════════════════════════════════════════════════════
# Trade dataclass
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    direction: str               # "long" or "short"
    entry_price: float
    exit_price: float
    stop_price: float
    tp_price: float
    pnl: float                   # dollar P&L after costs
    contracts: int
    strategy_used: str
    regime: str
    stop_type: str               # "stop_loss", "take_profit", "opposite_signal", "daily_limit"
    risk_amount: float           # dollar risk on this trade
    composite_score: float


# ═══════════════════════════════════════════════════════════════════════════
# TradeLog
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TradeLog:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    daily_limit_triggers: int = 0

    def to_dataframe(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                "Entry Date": t.entry_date,
                "Exit Date": t.exit_date,
                "Direction": t.direction,
                "Entry": round(t.entry_price, 4),
                "Exit": round(t.exit_price, 4),
                "Stop": round(t.stop_price, 4),
                "TP": round(t.tp_price, 4),
                "PnL": round(t.pnl, 2),
                "Contracts": t.contracts,
                "Strategy": t.strategy_used,
                "Regime": t.regime,
                "Exit Type": t.stop_type,
                "Risk $": round(t.risk_amount, 2),
                "Score": round(t.composite_score, 1),
            })
        return pd.DataFrame(rows)

    def summary(self) -> dict:
        if not self.trades:
            return {"total_trades": 0}
        df = self.to_dataframe()
        wins = df[df["PnL"] > 0]
        losses = df[df["PnL"] <= 0]
        gross_profit = wins["PnL"].sum() if len(wins) else 0.0
        gross_loss = abs(losses["PnL"].sum()) if len(losses) else 0.0
        return {
            "total_trades": len(df),
            "winners": len(wins),
            "losers": len(losses),
            "win_rate": round(100 * len(wins) / len(df), 1) if len(df) else 0.0,
            "total_pnl": round(df["PnL"].sum(), 2),
            "avg_win": round(wins["PnL"].mean(), 2) if len(wins) else 0.0,
            "avg_loss": round(losses["PnL"].mean(), 2) if len(losses) else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
            "max_drawdown": round(self._max_drawdown(), 2),
            "daily_limit_triggers": self.daily_limit_triggers,
        }

    def _max_drawdown(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        cummax = self.equity_curve.cummax()
        drawdown = self.equity_curve - cummax
        return float(drawdown.min())


# ═══════════════════════════════════════════════════════════════════════════
# TradeSimulator
# ═══════════════════════════════════════════════════════════════════════════

class TradeSimulator:
    def __init__(
        self,
        initial_capital: float = 10_000.0,
        point_value: float = 1.0,
        tick_size: float = 0.01,
        commission_per_contract: float = 0.005,
        slippage_ticks: int = 1,
        # Risk management
        max_daily_loss: float = 200.0,
        max_consecutive_losses: int = 2,
        max_risk_per_trade: float = 250.0,
        cooldown_bars: int = 3,
        # Trade parameters
        reward_ratio: float = 2.0,
        atr_stop_mult: float = 2.0,
        hard_dollar_stop: float = 100.0,
    ):
        self.initial_capital = initial_capital
        self.point_value = point_value
        self.tick_size = tick_size
        self.commission = commission_per_contract
        self.slippage_ticks = slippage_ticks

        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses
        self.max_risk_per_trade = max_risk_per_trade
        self.cooldown_bars = cooldown_bars

        self.reward_ratio = reward_ratio
        self.atr_stop_mult = atr_stop_mult
        self.hard_dollar_stop = hard_dollar_stop

    @classmethod
    def from_preset(cls, ticker: str, **overrides) -> "TradeSimulator":
        """Create simulator using instrument preset defaults."""
        preset = INSTRUMENT_PRESETS.get(ticker, {})
        params = {**preset, **overrides}
        return cls(**params)

    def simulate(self, df: pd.DataFrame, signals: pd.DataFrame,
                 meta: dict) -> TradeLog:
        """Run trade simulation over the dataset.

        Args:
            df: OHLCV DataFrame
            signals: Output from scorer (winner_strategy, direction, composite_score, ...)
            meta: Dict from run_full_pipeline containing 'indicators' and 'regime'
        """
        atr = meta["indicators"]["atr"]
        regime = meta["regime"]

        dates = df.index
        n = len(dates)
        slippage = self.slippage_ticks * self.tick_size

        trades: list[Trade] = []
        equity = self.initial_capital
        equity_points: list[tuple[pd.Timestamp, float]] = []

        # State tracking
        in_trade = False
        pending_signal_bar: int | None = None  # bar index where signal was received
        trade_entry_price = 0.0
        trade_stop = 0.0
        trade_tp = 0.0
        trade_direction = ""
        trade_strategy = ""
        trade_regime = ""
        trade_score = 0.0
        trade_contracts = 0
        trade_risk = 0.0
        trade_entry_date = dates[0]

        # Risk management state
        daily_pnl: dict[object, float] = {}  # date -> cumulative pnl for that day
        daily_consecutive_losses: dict[object, int] = {}
        daily_locked: set = set()  # dates where daily limit was hit
        consecutive_losses = 0
        last_exit_bar = -self.cooldown_bars - 1  # allow first trade immediately
        daily_limit_triggers = 0

        for i in range(n):
            bar_date = dates[i].date() if hasattr(dates[i], "date") else dates[i]

            # ── Check if we need to enter a trade from previous bar's signal ──
            if pending_signal_bar is not None and i == pending_signal_bar + 1:
                sig_idx = pending_signal_bar
                pending_signal_bar = None

                # Cooldown check
                if i - last_exit_bar < self.cooldown_bars:
                    pass  # skip, still in cooldown
                # Daily limit check
                elif bar_date in daily_locked:
                    pass  # skip, daily limit hit
                else:
                    sig_dir = signals["direction"].iat[sig_idx]
                    sig_strat = signals["winner_strategy"].iat[sig_idx]
                    sig_score = signals["composite_score"].iat[sig_idx]
                    sig_regime = regime.iat[sig_idx] if sig_idx < len(regime) else "undefined"
                    bar_atr = atr.iat[i] if not np.isnan(atr.iat[i]) else atr.iat[sig_idx]

                    if np.isnan(bar_atr) or bar_atr <= 0:
                        bar_atr = df["Close"].iat[i] * 0.02  # fallback: 2% of price

                    # Entry price: this bar's open + slippage against you
                    entry = df["Open"].iat[i]
                    if sig_dir == "long":
                        entry += slippage
                    else:
                        entry -= slippage

                    # Stop distance: tighter of ATR-based or hard dollar
                    atr_stop_dist = self.atr_stop_mult * bar_atr
                    dollar_stop_dist = self.hard_dollar_stop / self.point_value
                    stop_dist = min(atr_stop_dist, dollar_stop_dist)

                    # Risk per contract
                    risk_per_contract = stop_dist * self.point_value + self.commission

                    # Skip if risk exceeds limit
                    if risk_per_contract > self.max_risk_per_trade:
                        pass
                    else:
                        # Position sizing: 1 contract (fixed for simplicity)
                        contracts = 1
                        trade_risk_amount = risk_per_contract * contracts

                        # Set stop and target
                        if sig_dir == "long":
                            stop_price = entry - stop_dist
                            tp_price = entry + stop_dist * self.reward_ratio
                        else:
                            stop_price = entry + stop_dist
                            tp_price = entry - stop_dist * self.reward_ratio

                        # Enter trade
                        in_trade = True
                        trade_entry_price = entry
                        trade_stop = stop_price
                        trade_tp = tp_price
                        trade_direction = sig_dir
                        trade_strategy = sig_strat
                        trade_regime = sig_regime
                        trade_score = sig_score
                        trade_contracts = contracts
                        trade_risk = trade_risk_amount
                        trade_entry_date = dates[i]

            # ── Manage open position ──
            if in_trade:
                bar_high = df["High"].iat[i]
                bar_low = df["Low"].iat[i]
                bar_close = df["Close"].iat[i]

                exit_price = None
                exit_type = None

                if trade_direction == "long":
                    sl_hit = bar_low <= trade_stop
                    tp_hit = bar_high >= trade_tp
                else:
                    sl_hit = bar_high >= trade_stop
                    tp_hit = bar_low <= trade_tp

                # If both could hit in same bar, assume SL first (conservative)
                if sl_hit and tp_hit:
                    exit_price = trade_stop
                    exit_type = "stop_loss"
                elif sl_hit:
                    exit_price = trade_stop
                    exit_type = "stop_loss"
                elif tp_hit:
                    exit_price = trade_tp
                    exit_type = "take_profit"

                # Opposite signal check (exit at this bar's close, enter new next bar)
                if exit_price is None and signals["direction"].iat[i] != "":
                    sig_dir_now = signals["direction"].iat[i]
                    if sig_dir_now != trade_direction:
                        exit_price = bar_close
                        exit_type = "opposite_signal"

                if exit_price is not None:
                    # Calculate P&L
                    if trade_direction == "long":
                        price_pnl = (exit_price - trade_entry_price) * self.point_value
                    else:
                        price_pnl = (trade_entry_price - exit_price) * self.point_value

                    total_commission = self.commission * trade_contracts * 2  # round trip
                    pnl = price_pnl * trade_contracts - total_commission

                    equity += pnl

                    trade = Trade(
                        entry_date=trade_entry_date,
                        exit_date=dates[i],
                        direction=trade_direction,
                        entry_price=trade_entry_price,
                        exit_price=exit_price,
                        stop_price=trade_stop,
                        tp_price=trade_tp,
                        pnl=pnl,
                        contracts=trade_contracts,
                        strategy_used=trade_strategy,
                        regime=trade_regime,
                        stop_type=exit_type,
                        risk_amount=trade_risk,
                        composite_score=trade_score,
                    )
                    trades.append(trade)

                    in_trade = False
                    last_exit_bar = i

                    # Update daily risk tracking
                    daily_pnl[bar_date] = daily_pnl.get(bar_date, 0.0) + pnl

                    if pnl <= 0:
                        consecutive_losses += 1
                        daily_consecutive_losses[bar_date] = \
                            daily_consecutive_losses.get(bar_date, 0) + 1
                    else:
                        consecutive_losses = 0
                        daily_consecutive_losses.setdefault(bar_date, 0)

                    # Check daily loss limit
                    if (daily_pnl.get(bar_date, 0.0) <= -self.max_daily_loss
                            or daily_consecutive_losses.get(bar_date, 0) >= self.max_consecutive_losses):
                        daily_locked.add(bar_date)
                        daily_limit_triggers += 1

            # ── Record pending signal (will try to enter next bar) ──
            if not in_trade and signals["direction"].iat[i] != "":
                if bar_date not in daily_locked and i - last_exit_bar >= self.cooldown_bars:
                    pending_signal_bar = i

            # Record equity at end of each bar
            equity_points.append((dates[i], equity))

        # Close any open trade at last bar's close
        if in_trade:
            exit_price = df["Close"].iat[-1]
            if trade_direction == "long":
                price_pnl = (exit_price - trade_entry_price) * self.point_value
            else:
                price_pnl = (trade_entry_price - exit_price) * self.point_value
            total_commission = self.commission * trade_contracts * 2
            pnl = price_pnl * trade_contracts - total_commission
            equity += pnl
            trades.append(Trade(
                entry_date=trade_entry_date,
                exit_date=dates[-1],
                direction=trade_direction,
                entry_price=trade_entry_price,
                exit_price=exit_price,
                stop_price=trade_stop,
                tp_price=trade_tp,
                pnl=pnl,
                contracts=trade_contracts,
                strategy_used=trade_strategy,
                regime=trade_regime,
                stop_type="end_of_data",
                risk_amount=trade_risk,
                composite_score=trade_score,
            ))
            equity_points[-1] = (dates[-1], equity)

        # Build equity curve
        eq_dates, eq_vals = zip(*equity_points) if equity_points else ([], [])
        equity_series = pd.Series(eq_vals, index=pd.DatetimeIndex(eq_dates), dtype=float)

        log = TradeLog(
            trades=trades,
            equity_curve=equity_series,
            daily_limit_triggers=daily_limit_triggers,
        )
        return log


# ═══════════════════════════════════════════════════════════════════════════
# Summary printer
# ═══════════════════════════════════════════════════════════════════════════

def print_trade_log(ticker: str, log: TradeLog) -> None:
    """Print comprehensive trade simulation results."""
    s = log.summary()
    print(f"\n{'=' * 70}")
    print(f"  TRADE SIMULATION — {ticker}")
    print(f"{'=' * 70}")

    if s["total_trades"] == 0:
        print("  No trades executed.\n")
        return

    print(f"  Total trades:        {s['total_trades']:>6d}")
    print(f"  Winners:             {s['winners']:>6d}  ({s['win_rate']:.1f}%)")
    print(f"  Losers:              {s['losers']:>6d}")
    print(f"  Total PnL:           ${s['total_pnl']:>10.2f}")
    print(f"  Avg Win:             ${s['avg_win']:>10.2f}")
    print(f"  Avg Loss:            ${s['avg_loss']:>10.2f}")
    print(f"  Profit Factor:       {s['profit_factor']:>10.2f}")
    print(f"  Max Drawdown:        ${s['max_drawdown']:>10.2f}")
    print(f"  Daily limit triggers:{s['daily_limit_triggers']:>6d}")
    print()

    # Equity curve shape
    eq = log.equity_curve
    if not eq.empty:
        start_eq = eq.iloc[0]
        end_eq = eq.iloc[-1]
        peak = eq.max()
        trough = eq.min()
        net = end_eq - start_eq
        shape = "UP" if net > 50 else "DOWN" if net < -50 else "FLAT"
        print(f"  Equity curve:  start=${start_eq:.0f}  end=${end_eq:.0f}  "
              f"peak=${peak:.0f}  trough=${trough:.0f}  shape={shape}")
    print()

    # Exit type breakdown
    df = log.to_dataframe()
    exit_counts = df["Exit Type"].value_counts()
    print("  Exit type breakdown:")
    for etype, count in exit_counts.items():
        avg_pnl = df.loc[df["Exit Type"] == etype, "PnL"].mean()
        print(f"    {etype:<18s}  {count:>4d} trades  avg PnL=${avg_pnl:>8.2f}")
    print()

    # Strategy breakdown
    strat_counts = df["Strategy"].value_counts()
    print("  Strategy breakdown:")
    for sname, count in strat_counts.items():
        avg_pnl = df.loc[df["Strategy"] == sname, "PnL"].mean()
        wr = 100 * (df.loc[df["Strategy"] == sname, "PnL"] > 0).mean()
        print(f"    {sname:<22s}  {count:>3d} trades  "
              f"avg=${avg_pnl:>8.2f}  WR={wr:.0f}%")
    print()

    # First 10 trades
    head = df.head(10)
    print("  First 10 trades:")
    print(tabulate(
        head[["Entry Date", "Exit Date", "Direction", "Entry", "Exit",
              "Stop", "TP", "PnL", "Exit Type", "Strategy", "Regime", "Score"]].values.tolist(),
        headers=["Entry", "Exit", "Dir", "Entry$", "Exit$",
                 "Stop$", "TP$", "PnL", "Exit Type", "Strategy", "Regime", "Score"],
        tablefmt="simple",
        floatfmt=".2f",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from data_loader import load_sierra_dly
    from scorer import run_full_pipeline

    tickers = [
        ("SPY", "data/SPY.dly"),
        ("CL",  "data/CL.dly"),
    ]

    for ticker, path in tickers:
        df = load_sierra_dly(path)
        print(f"\nLoading {ticker}: {len(df)} rows, "
              f"{df.index.min().date()} → {df.index.max().date()}")

        # Run scoring pipeline
        signals, meta = run_full_pipeline(df, min_composite=50.0, expiry_bars=3)

        # Create simulator with instrument preset
        sim = TradeSimulator.from_preset(ticker, initial_capital=10_000.0)
        log = sim.simulate(df, signals, meta)

        print_trade_log(ticker, log)
