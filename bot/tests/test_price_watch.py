"""가격 알림 유닛테스트 — 접근/도달/방향 경계를 손 계산 값으로 고정."""

from btc_bot.monitor.price_watch import (
    PriceAlertState,
    detect_direction,
    evaluate_price_alert,
    format_price_alert,
)


def test_target_below_current_watches_down():
    assert detect_direction(current_price=81_000, target=79_900) == "down"


def test_target_above_current_watches_up():
    assert detect_direction(current_price=81_000, target=85_000) == "up"


def test_down_hit_when_price_touches_target():
    state = PriceAlertState(target=79_900, direction="down", near_pct=1.0)
    assert evaluate_price_alert(79_900, state) == "hit"
    assert evaluate_price_alert(79_850, state) == "hit"


def test_down_near_within_pct():
    # 목표 79,900의 1% = 799 → 80,600은 0.88% 차이로 접근 알림
    state = PriceAlertState(target=79_900, direction="down", near_pct=1.0)
    assert evaluate_price_alert(80_600, state) == "near"


def test_down_far_is_silent():
    state = PriceAlertState(target=79_900, direction="down", near_pct=1.0)
    assert evaluate_price_alert(82_000, state) is None


def test_near_fires_only_once():
    state = PriceAlertState(target=79_900, direction="down", near_pct=1.0, near_sent=True)
    assert evaluate_price_alert(80_600, state) is None


def test_up_hit_when_price_rises_to_target():
    state = PriceAlertState(target=85_000, direction="up", near_pct=1.0)
    assert evaluate_price_alert(85_000, state) == "hit"
    assert evaluate_price_alert(79_000, state) is None


def test_near_pct_zero_disables_near_alert():
    state = PriceAlertState(target=79_900, direction="down", near_pct=0.0)
    assert evaluate_price_alert(79_901, state) is None


def test_alert_messages_mention_prices():
    state = PriceAlertState(target=79_899.8, direction="down", near_pct=1.0)
    hit = format_price_alert("hit", 79_899.8, state)
    near = format_price_alert("near", 80_500.0, state)
    assert "79,899.8" in hit and "도달" in hit
    assert "79,899.8" in near and "접근" in near
