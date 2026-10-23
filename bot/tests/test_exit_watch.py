"""매도 감시 유닛테스트 — 손절/armed/트레일링 경계를 손 계산 값으로 고정.

기준 시나리오: 매수가 $80,000, stop 4%, arm 6%, trail 4%
→ 손절선 $76,800 / 트레일링 발동 $84,800
"""

from btc_bot.monitor.exit_watch import ExitWatchState, evaluate_exit, format_exit_alert


def make_state(peak: float = 80_000, armed: bool = False) -> ExitWatchState:
    return ExitWatchState(
        entry=80_000, peak=peak, armed=armed,
        stop_loss_pct=0.04, arm_profit_pct=0.06, trail_pct=0.04,
    )


def test_quiet_when_price_in_range():
    kind, state = evaluate_exit(81_000, make_state())
    assert kind is None
    assert state.peak == 81_000  # 고점은 갱신


def test_stop_at_minus_4pct():
    kind, _ = evaluate_exit(76_800, make_state())
    assert kind == "stop"
    kind, _ = evaluate_exit(76_801, make_state())
    assert kind is None


def test_armed_at_plus_6pct():
    kind, state = evaluate_exit(84_800, make_state())
    assert kind == "armed"
    assert state.armed is True
    assert state.peak == 84_800


def test_armed_fires_only_once():
    kind, _ = evaluate_exit(85_000, make_state(peak=85_000, armed=True))
    assert kind is None


def test_trail_after_armed():
    # 고점 $90,000 → 익절선 $86,400
    state = make_state(peak=90_000, armed=True)
    kind, _ = evaluate_exit(86_400, state)
    assert kind == "trail"
    kind, _ = evaluate_exit(86_401, state)
    assert kind is None


def test_no_trail_before_armed():
    # armed 전엔 고점 대비 4% 빠져도 침묵 (손절선 위라면)
    state = make_state(peak=83_000, armed=False)
    kind, _ = evaluate_exit(79_000, state)
    assert kind is None


def test_crash_through_both_prefers_stop():
    # armed 상태에서 손절선까지 폭락하면 손절로 보고
    state = make_state(peak=90_000, armed=True)
    kind, _ = evaluate_exit(76_000, state)
    assert kind == "stop"


def test_peak_keeps_rising_moves_trail_up():
    state = make_state(peak=85_000, armed=True)
    _, state = evaluate_exit(92_000, state)
    assert state.peak == 92_000
    assert state.trail_price == 92_000 * 0.96


def test_alert_messages():
    state = make_state(peak=90_000, armed=True)
    assert "손절" in format_exit_alert("stop", 76_500, state)
    assert "익절" in format_exit_alert("trail", 86_000, state)
    assert "고점" in format_exit_alert("armed", 84_800, state)
