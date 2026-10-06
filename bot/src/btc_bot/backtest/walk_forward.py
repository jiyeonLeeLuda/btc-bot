from dataclasses import dataclass

import pandas as pd

from btc_bot.backtest.event_engine import run_event_backtest
from btc_bot.strategies.mean_reversion import MeanReversion


@dataclass(frozen=True)
class WindowResult:
    ref_window: int
    train_return_pct: float
    test_return_pct: float


@dataclass(frozen=True)
class OosReport:
    train_period: tuple[pd.Timestamp, pd.Timestamp]
    test_period: tuple[pd.Timestamp, pd.Timestamp]
    train_bench_pct: float
    test_bench_pct: float
    rows: list[WindowResult]
    best_train_window: int
    best_train_return_pct: float
    best_window_test_return_pct: float


def split_candles(
    candles: pd.DataFrame, train_frac: float = 0.5
) -> tuple[pd.DataFrame, pd.DataFrame]:
    split = int(len(candles) * train_frac)
    return candles.iloc[:split], candles.iloc[split:]


def run_oos(
    candles: pd.DataFrame,
    windows: range,
    fee_rate: float,
    initial_cash: float,
    trend_filter_window: int = 0,
) -> OosReport:
    """앞 절반(train)에서 기준을 고르고, 뒷 절반(test)에 적용해 요행 여부를 검증.

    지표(이동평균)는 전체 시계열에서 한 번 계산한 뒤 잘라서 넘긴다. 그래야
    test 절반 앞부분이 장기선 워밍업으로 날아가지 않는다(경계 연속성 유지).
    """
    close = candles["close"]
    split = int(len(candles) * 0.5)
    trend_ma_full = (
        close.rolling(trend_filter_window).mean() if trend_filter_window > 0 else None
    )

    def _slice(series: pd.Series | None, start: int, stop: int) -> pd.Series | None:
        return None if series is None else series.iloc[start:stop]

    train, test = candles.iloc[:split], candles.iloc[split:]

    rows: list[WindowResult] = []
    best_train_window = windows.start
    best_train_return = float("-inf")
    best_window_test_return = 0.0

    train_bench = test_bench = 0.0
    for w in windows:
        ref_full = close.rolling(w).mean()
        strat = MeanReversion(ref_window=w, trend_filter_window=trend_filter_window)
        tr = run_event_backtest(
            train, strat, fee_rate, initial_cash,
            ref_avg=ref_full.iloc[:split],
            trend_ma=_slice(trend_ma_full, 0, split),
        )
        te = run_event_backtest(
            test, strat, fee_rate, initial_cash,
            ref_avg=ref_full.iloc[split:],
            trend_ma=_slice(trend_ma_full, split, len(candles)),
        )
        train_bench, test_bench = tr.buy_and_hold_pct, te.buy_and_hold_pct
        rows.append(WindowResult(w, tr.total_return_pct, te.total_return_pct))
        if tr.total_return_pct > best_train_return:
            best_train_return = tr.total_return_pct
            best_train_window = w
            best_window_test_return = te.total_return_pct

    return OosReport(
        train_period=(train.index[0], train.index[-1]),
        test_period=(test.index[0], test.index[-1]),
        train_bench_pct=train_bench,
        test_bench_pct=test_bench,
        rows=rows,
        best_train_window=best_train_window,
        best_train_return_pct=best_train_return,
        best_window_test_return_pct=best_window_test_return,
    )
