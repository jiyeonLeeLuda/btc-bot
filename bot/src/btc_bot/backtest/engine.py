from dataclasses import dataclass

import pandas as pd

from btc_bot.strategies.base import Strategy


@dataclass(frozen=True)
class BacktestResult:
    strategy_name: str
    total_return_pct: float
    buy_and_hold_pct: float
    max_drawdown_pct: float
    num_trades: int
    equity_curve: pd.Series


def run_backtest(
    candles: pd.DataFrame,
    strategy: Strategy,
    fee_rate: float,
    initial_cash: float,
) -> BacktestResult:
    """Candle-close backtest.

    Signal at candle t is acted on at the close of t (simplification:
    in reality you'd fill at the next open — good first discussion topic).
    """
    signals = strategy.generate_signals(candles)
    close = candles["close"]

    # 포지션 변화가 있는 지점마다 수수료 차감
    position_changes = signals.diff().fillna(signals.iloc[0]).abs()
    num_trades = int(position_changes.sum())

    market_returns = close.pct_change().fillna(0.0)
    strategy_returns = market_returns * signals.shift(1).fillna(0)
    strategy_returns = strategy_returns - position_changes * fee_rate

    equity = initial_cash * (1 + strategy_returns).cumprod()
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max

    total_return = (equity.iloc[-1] / initial_cash - 1) * 100
    buy_and_hold = (close.iloc[-1] / close.iloc[0] - 1) * 100

    return BacktestResult(
        strategy_name=strategy.name,
        total_return_pct=round(total_return, 2),
        buy_and_hold_pct=round(buy_and_hold, 2),
        max_drawdown_pct=round(drawdown.min() * 100, 2),
        num_trades=num_trades,
        equity_curve=equity,
    )
