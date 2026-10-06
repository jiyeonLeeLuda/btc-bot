"""엔진 유닛테스트.

각 테스트는 '답을 손으로 미리 계산한' 아주 작은 가짜 캔들을 넣고,
엔진이 그 답을 내놓는지 확인한다. 백테스트 숫자를 믿을 근거.
"""

import pandas as pd

from btc_bot.backtest.event_engine import run_event_backtest
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


def test_no_dip_no_trade():
    # 가격이 평균 아래로 안 내려오면 한 번도 안 산다.
    candles = make_candles([100, 100, 100, 100, 100])
    strat = MeanReversion(ref_window=3, buy_dip_pct=0.05)
    result = run_event_backtest(candles, strat, FEE, CASH)
    assert result.num_trades == 0
    assert result.total_return_pct == 0.0


def test_dip_then_stoploss():
    # i=4에서 90으로 눌려 매수 → i=5에서 86으로 더 빠져 손절(산값 -4%).
    candles = make_candles([100, 100, 100, 100, 90, 86])
    strat = MeanReversion(ref_window=3, buy_dip_pct=0.05, stop_loss_pct=0.04)
    result = run_event_backtest(candles, strat, FEE, CASH)
    assert result.num_trades == 1
    assert result.trades[0].reason == "stop"
    assert result.trades[0].return_pct == -4.44  # 86/90-1


def test_dip_arm_then_trailing_exit():
    # 90 매수 → 97,100으로 +6% 넘겨 트레일링 무장 → 95로 고점(100) 대비 -4% 꺾여 익절.
    candles = make_candles([100, 100, 100, 100, 90, 97, 100, 95])
    strat = MeanReversion(
        ref_window=3, buy_dip_pct=0.05, stop_loss_pct=0.04,
        arm_profit_pct=0.06, trail_pct=0.04,
    )
    result = run_event_backtest(candles, strat, FEE, CASH)
    assert result.num_trades == 1
    assert result.trades[0].reason == "trail"
    assert result.trades[0].return_pct == 5.56  # 95/90-1


def test_fee_applied_on_buy():
    # 매수 직후 평가액은 수수료만큼 줄어든다 (같은 봉 종가 기준).
    candles = make_candles([100, 100, 100, 100, 90, 86])
    strat = MeanReversion(ref_window=3, buy_dip_pct=0.05)
    result = run_event_backtest(candles, strat, FEE, CASH)
    equity_at_buy = result.equity_curve.iloc[4]  # 90으로 매수한 봉
    assert equity_at_buy == CASH * (1 - FEE)  # 9990.0


def test_trend_filter_blocks_buy():
    # 장기선(=1000) 위일 때만 사는데 가격이 늘 그 아래면 한 번도 안 산다 → 현금 유지 0%.
    # (하락장 test가 전부 0.0% 나온 해석 "거래를 아예 안 했다"를 검증)
    closes = [100, 100, 100, 100, 90, 86]
    candles = make_candles(closes)
    trend_ma = pd.Series([1000.0] * len(closes), index=candles.index)
    strat = MeanReversion(ref_window=3, buy_dip_pct=0.05, trend_filter_window=5)
    result = run_event_backtest(candles, strat, FEE, CASH, trend_ma=trend_ma)
    assert result.num_trades == 0
    assert result.total_return_pct == 0.0


def test_trend_filter_regime_exit():
    # 장기선 아래(80)일 때 매수 → 다음 봉 장기선(95)이 가격 위로 올라오면 regime 사유로 청산.
    closes = [100, 100, 100, 100, 90, 89]
    candles = make_candles(closes)
    trend_ma = pd.Series([80, 80, 80, 80, 80, 95], index=candles.index, dtype=float)
    strat = MeanReversion(
        ref_window=3, buy_dip_pct=0.05, stop_loss_pct=0.04, trend_filter_window=5,
    )
    result = run_event_backtest(candles, strat, FEE, CASH, trend_ma=trend_ma)
    assert result.num_trades == 1
    assert result.trades[0].reason == "regime"
    assert result.trades[0].return_pct == -1.11  # 89/90-1


def test_precomputed_ref_avg_matches_internal():
    # ref_avg를 미리 계산해 넘긴 결과가 엔진 내부 계산과 동일해야 한다(OOS 슬라이싱 경로 검증).
    candles = make_candles([100, 100, 100, 100, 90, 97, 100, 95])
    strat = MeanReversion(ref_window=3, buy_dip_pct=0.05)
    internal = run_event_backtest(candles, strat, FEE, CASH)
    precomputed = run_event_backtest(
        candles, strat, FEE, CASH,
        ref_avg=candles["close"].rolling(strat.ref_window).mean(),
    )
    assert internal.total_return_pct == precomputed.total_return_pct
    assert internal.num_trades == precomputed.num_trades
