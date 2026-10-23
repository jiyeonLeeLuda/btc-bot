"""가격 알림: 목표가에 접근/도달하면 알림을 보낸다.

용도 예: 거래소에 $79,899.8 지정가 매수를 걸어두고, 체결권에 들어오면
디스코드로 연락받기. 도달 알림을 보내면 감시를 끝낸다(원샷).
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from rich.console import Console

from btc_bot.data.fetcher import fetch_last_price
from btc_bot.notify import Notifier

console = Console()


@dataclass(frozen=True)
class PriceAlertState:
    target: float
    direction: str        # "down" = 하락해서 목표가 터치, "up" = 상승해서 터치
    near_pct: float       # 목표가와 이 % 이내로 좁혀지면 접근 알림 (0이면 끔)
    near_sent: bool = False


def detect_direction(current_price: float, target: float) -> str:
    """목표가가 현재가보다 낮으면 '내려와서 닿는' 감시, 높으면 '올라가서 닿는' 감시."""
    return "down" if target < current_price else "up"


def evaluate_price_alert(price: float, state: PriceAlertState) -> str | None:
    """이번 가격으로 보낼 알림 종류를 돌려준다: "hit" | "near" | None."""
    hit = price <= state.target if state.direction == "down" else price >= state.target
    if hit:
        return "hit"
    if state.near_pct > 0 and not state.near_sent:
        gap_pct = abs(price / state.target - 1) * 100
        if gap_pct <= state.near_pct:
            return "near"
    return None


def format_price_alert(kind: str, price: float, state: PriceAlertState) -> str:
    arrow = "⬇️" if state.direction == "down" else "⬆️"
    if kind == "hit":
        return (
            f"🎯 목표가 도달 {arrow}\n"
            f"BTC 현재 ${price:,.1f} — 목표 ${state.target:,.1f}에 닿았어요.\n"
            f"걸어둔 주문이 있다면 체결됐는지 거래소를 확인하세요."
        )
    gap_pct = abs(price / state.target - 1) * 100
    return (
        f"👀 목표가 접근 {arrow}\n"
        f"BTC 현재 ${price:,.1f} — 목표 ${state.target:,.1f}까지 {gap_pct:.2f}% 남았어요."
    )


def run_price_watch(
    symbol: str,
    target: float,
    notifier: Notifier,
    poll_seconds: int = 60,
    near_pct: float = 1.0,
) -> None:
    """목표가 도달까지 가격을 감시한다. 도달 알림 후 종료 (Ctrl+C로 중단).

    규칙:
    - 접근 알림(near_pct% 이내)은 한 번만
    - 도달 알림을 보내면 루프 종료
    - 네트워크/알림 오류는 루프를 죽이지 않는다
    """
    first_price = fetch_last_price(symbol)
    direction = detect_direction(first_price, target)
    state = PriceAlertState(target=target, direction=direction, near_pct=near_pct)
    label = "하락 터치" if direction == "down" else "상승 터치"
    console.print(
        f"[bold]가격 감시 시작[/] {symbol} 목표 ${target:,.1f} ({label}) / "
        f"현재 ${first_price:,.1f} / {poll_seconds}초마다"
    )

    price = first_price
    while True:
        try:
            kind = evaluate_price_alert(price, state)
            now = datetime.now(timezone.utc).isoformat()
            gap_pct = (price / target - 1) * 100
            console.print(f"{now}  가격 ${price:,.1f}  목표 대비 {gap_pct:+.2f}%")
            if kind is not None:
                notifier.send(format_price_alert(kind, price, state))
            if kind == "hit":
                console.print("[green]목표가 도달 — 감시 종료[/]")
                return
            if kind == "near":
                state = PriceAlertState(
                    target=state.target, direction=state.direction,
                    near_pct=state.near_pct, near_sent=True,
                )
        except Exception as error:  # noqa: BLE001 - 감시 루프는 멈추면 안 됨
            console.print(f"[red]감시 오류(계속 진행):[/] {error}")
        time.sleep(poll_seconds)
        try:
            price = fetch_last_price(symbol)
        except Exception as error:  # noqa: BLE001
            console.print(f"[red]시세 조회 오류(계속 진행):[/] {error}")
