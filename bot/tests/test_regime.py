"""장세 판단 유닛테스트 — 손 계산한 가짜 데이터로 up/down 경계를 고정."""

import pandas as pd
import pytest

from btc_bot.monitor.regime import detect_regime, format_alert


def make_candles(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame({"close": closes}, index=idx)


def test_price_above_ma_is_up():
    # 평균 100, 현재가 110 → 상승장, 갭 +10%
    candles = make_candles([100, 100, 100, 100, 110])
    status = detect_regime(candles, window=5)
    assert status.regime == "up"
    assert status.long_ma == 102.0  # (100+100+100+100+110)/5
    assert status.gap_pct == round((110 / 102 - 1) * 100, 2)


def test_price_below_ma_is_down():
    # 현재가가 장기 평균보다 낮으면 하락장
    candles = make_candles([120, 120, 120, 120, 90])
    status = detect_regime(candles, window=5)
    assert status.regime == "down"
    assert status.gap_pct < 0


def test_insufficient_candles_raises():
    candles = make_candles([100, 100])
    with pytest.raises(ValueError):
        detect_regime(candles, window=200)


def test_alert_message_mentions_downtrend():
    candles = make_candles([120, 120, 120, 120, 90])
    status = detect_regime(candles, window=5)
    msg = format_alert(status, window=5)
    assert "하락장" in msg
