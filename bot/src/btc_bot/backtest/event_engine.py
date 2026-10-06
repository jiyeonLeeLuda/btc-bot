from dataclasses import dataclass

import pandas as pd

from btc_bot.strategies.mean_reversion import MeanReversion


@dataclass(frozen=True)
class Trade:
    buy_time: pd.Timestamp
    sell_time: pd.Timestamp
    buy_price: float
    sell_price: float
    reason: str  # "stop" | "trail" | "regime"
    return_pct: float


@dataclass(frozen=True)
class EventBacktestResult:
    strategy_name: str
    total_return_pct: float
    buy_and_hold_pct: float
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: float
    avg_hold_days: float
    trades: list[Trade]
    equity_curve: pd.Series


def run_event_backtest(
    candles: pd.DataFrame,
    strategy: MeanReversion,
    fee_rate: float,
    initial_cash: float,
    ref_avg: pd.Series | None = None,
    trend_ma: pd.Series | None = None,
) -> EventBacktestResult:
    """한 봉씩 상태를 추적하는 이벤트 방식 백테스트.

    ref_avg / trend_ma를 넘기면 그걸 쓰고(OOS에서 경계 워밍업 손실 방지용),
    안 넘기면 주어진 candles로 계산한다.

    단순화(다음 학습 주제): 신호 판단과 체결을 같은 봉의 종가로 처리(약한 룩어헤드),
    슬리피지 없음, 현물 long/flat만.
    """
    close = candles["close"]
    if ref_avg is None:
        ref_avg = close.rolling(strategy.ref_window).mean()
    use_filter = strategy.trend_filter_window > 0
    if use_filter and trend_ma is None:
        trend_ma = close.rolling(strategy.trend_filter_window).mean()

    cash = initial_cash
    btc = 0.0
    buy_price = 0.0
    buy_time = close.index[0]
    peak = 0.0
    armed = False

    equity: list[float] = []
    trades: list[Trade] = []

    for i in range(len(close)):
        ts = close.index[i]
        price = float(close.iloc[i])
        avg = ref_avg.iloc[i]

        uptrend = True
        if use_filter:
            tm = trend_ma.iloc[i]
            uptrend = pd.notna(tm) and price > tm

        if btc == 0.0:
            if pd.notna(avg) and price < avg * (1 - strategy.buy_dip_pct) and uptrend:
                btc = cash * (1 - fee_rate) / price
                cash = 0.0
                buy_price = price
                buy_time = ts
                peak = price
                armed = False
        else:
            peak = max(peak, price)
            if price >= buy_price * (1 + strategy.arm_profit_pct):
                armed = True

            stop_hit = price <= buy_price * (1 - strategy.stop_loss_pct)
            trail_hit = armed and price <= peak * (1 - strategy.trail_pct)
            regime_hit = use_filter and not uptrend

            if stop_hit or trail_hit or regime_hit:
                cash = btc * price * (1 - fee_rate)
                reason = "stop" if stop_hit else "trail" if trail_hit else "regime"
                trades.append(Trade(
                    buy_time=buy_time,
                    sell_time=ts,
                    buy_price=buy_price,
                    sell_price=price,
                    reason=reason,
                    return_pct=round((price / buy_price - 1) * 100, 2),
                ))
                btc = 0.0

        equity.append(cash + btc * price)

    equity_curve = pd.Series(equity, index=close.index)
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max

    wins = [t for t in trades if t.return_pct > 0]
    hold_days = [
        (t.sell_time - t.buy_time).total_seconds() / 86400 for t in trades
    ]

    return EventBacktestResult(
        strategy_name=strategy.name,
        total_return_pct=round((equity_curve.iloc[-1] / initial_cash - 1) * 100, 2),
        buy_and_hold_pct=round((close.iloc[-1] / close.iloc[0] - 1) * 100, 2),
        max_drawdown_pct=round(drawdown.min() * 100, 2),
        num_trades=len(trades),
        win_rate_pct=round(100 * len(wins) / len(trades), 1) if trades else 0.0,
        avg_hold_days=round(sum(hold_days) / len(hold_days), 1) if hold_days else 0.0,
        trades=trades,
        equity_curve=equity_curve,
    )
