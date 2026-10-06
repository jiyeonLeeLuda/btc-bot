"""OOS 슬라이싱 정렬 테스트.

run_oos가 캔들을 반으로 자를 때, 지표(이동평균)도 같은 경계로 잘려
독립 계산과 일치하는지 검증한다. (회고에서 의심했던 '슬라이싱 오정렬' 방지)
"""

import pandas as pd

from btc_bot.backtest.event_engine import run_event_backtest
from btc_bot.backtest.walk_forward import run_oos
from btc_bot.strategies.mean_reversion import MeanReversion

FEE = 0.001
CASH = 10_000.0


def make_candles(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": [1.0] * len(closes)},
        index=idx,
    )


def test_oos_split_is_clean_and_aligned():
    # 20봉: 앞 10 train, 뒤 10 test. 중간에 눌림을 넣어 거래가 생기게.
    closes = [100, 100, 100, 100, 90, 97, 100, 100, 100, 100,
              100, 100, 100, 92, 100, 100, 100, 88, 100, 100]
    candles = make_candles(closes)
    split = 10

    report = run_oos(candles, range(3, 4), FEE, CASH, trend_filter_window=0)

    # ① 분할 경계가 정확하고 겹치지 않는다.
    assert report.train_period == (candles.index[0], candles.index[split - 1])
    assert report.test_period == (candles.index[split], candles.index[-1])

    # ② run_oos가 보고한 숫자가, 같은 방식으로 수동 슬라이스한 독립 백테스트와 일치한다.
    ref_full = candles["close"].rolling(3).mean()
    strat = MeanReversion(ref_window=3)
    train_indep = run_event_backtest(
        candles.iloc[:split], strat, FEE, CASH, ref_avg=ref_full.iloc[:split],
    )
    test_indep = run_event_backtest(
        candles.iloc[split:], strat, FEE, CASH, ref_avg=ref_full.iloc[split:],
    )
    assert report.rows[0].train_return_pct == train_indep.total_return_pct
    assert report.rows[0].test_return_pct == test_indep.total_return_pct
