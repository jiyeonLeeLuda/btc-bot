"""매도 감시: 매수가를 알려주면 전략의 매도 규칙대로 "팔 때"를 알려준다.

규칙 (평균회귀 전략과 동일):
- 손절: 매수가 대비 -stop_loss_pct 아래로 떨어지면 → 알림 후 종료
- 트레일링 익절: 매수가 대비 +arm_profit_pct를 찍으면 발동(armed),
  이후 고점 대비 -trail_pct 빠지면 → 알림 후 종료
- armed 전환 순간에도 한 번 알림 ("이제부터 고점 추적 시작")

고점(peak)과 armed 상태는 파일에 저장해서, 봇을 재시작해도 이어서 감시한다.
"""

import json
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from btc_bot.data.fetcher import fetch_last_price
from btc_bot.notify import Notifier

console = Console()


@dataclass(frozen=True)
class ExitWatchState:
    entry: float            # 매수가
    peak: float             # 매수 후 최고가 (트레일링 기준)
    armed: bool             # +arm_profit_pct 도달 여부
    stop_loss_pct: float
    arm_profit_pct: float
    trail_pct: float

    @property
    def stop_price(self) -> float:
        return self.entry * (1 - self.stop_loss_pct)

    @property
    def arm_price(self) -> float:
        return self.entry * (1 + self.arm_profit_pct)

    @property
    def trail_price(self) -> float:
        return self.peak * (1 - self.trail_pct)


def evaluate_exit(price: float, state: ExitWatchState) -> tuple[str | None, ExitWatchState]:
    """이번 가격으로 보낼 알림과 갱신된 상태를 돌려준다.

    알림 종류: "stop"(손절) | "trail"(익절) | "armed"(트레일링 발동) | None
    판정 순서는 백테스트 엔진과 동일: peak 갱신 → armed 승격 → stop → trail.
    """
    new_state = replace(state, peak=max(state.peak, price))
    just_armed = not new_state.armed and price >= new_state.arm_price
    if just_armed:
        new_state = replace(new_state, armed=True)

    if price <= new_state.stop_price:
        return "stop", new_state
    if new_state.armed and price <= new_state.trail_price:
        return "trail", new_state
    if just_armed:
        return "armed", new_state
    return None, new_state


def format_exit_alert(kind: str, price: float, state: ExitWatchState) -> str:
    pnl_pct = (price / state.entry - 1) * 100
    base = f"BTC 현재 ${price:,.1f} (매수가 ${state.entry:,.1f} 대비 {pnl_pct:+.2f}%)"
    if kind == "stop":
        return (
            f"🛑 손절 신호 — 팔 때예요\n{base}\n"
            f"손절선 ${state.stop_price:,.1f} 아래로 내려왔어요. "
            f"전략 규칙상 여기서 끊고 다음 기회를 기다려요."
        )
    if kind == "trail":
        return (
            f"💰 익절 신호 — 팔 때예요\n{base}\n"
            f"고점 ${state.peak:,.1f} 대비 {state.trail_pct:.0%} 빠졌어요 "
            f"(트레일링 익절선 ${state.trail_price:,.1f})."
        )
    return (
        f"🔔 트레일링 익절 발동\n{base}\n"
        f"+{state.arm_profit_pct:.0%} 목표를 찍었어요. 이제부터 고점을 추적하다 "
        f"고점 대비 {state.trail_pct:.0%} 빠지면 매도 알림을 보낼게요."
    )


def load_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_state(path: Path, state: ExitWatchState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "entry": state.entry,
        "peak": state.peak,
        "armed": state.armed,
        "updated": datetime.now(timezone.utc).isoformat(),
    }))


def run_exit_watch(
    symbol: str,
    entry: float,
    state_path: Path,
    notifier: Notifier,
    poll_seconds: int = 60,
    stop_loss_pct: float = 0.04,
    arm_profit_pct: float = 0.06,
    trail_pct: float = 0.04,
) -> None:
    """매도 신호(손절/익절)까지 가격을 감시한다. 매도 알림 후 종료 (Ctrl+C로 중단)."""
    saved = load_state(state_path)
    if saved and saved.get("entry") == entry:
        peak, armed = float(saved["peak"]), bool(saved["armed"])
        console.print(f"[dim]이전 감시 이어받음: 고점 ${peak:,.1f}, armed={armed}[/]")
    else:
        peak, armed = entry, False

    state = ExitWatchState(
        entry=entry, peak=peak, armed=armed,
        stop_loss_pct=stop_loss_pct, arm_profit_pct=arm_profit_pct, trail_pct=trail_pct,
    )
    console.print(
        f"[bold]매도 감시 시작[/] {symbol} 매수가 ${entry:,.1f} / "
        f"손절 ${state.stop_price:,.1f} / 트레일링 발동 ${state.arm_price:,.1f} / "
        f"{poll_seconds}초마다"
    )

    while True:
        try:
            price = fetch_last_price(symbol)
            kind, state = evaluate_exit(price, state)
            save_state(state_path, state)
            now = datetime.now(timezone.utc).isoformat()
            pnl_pct = (price / entry - 1) * 100
            tracker = f"고점 ${state.peak:,.1f} 익절선 ${state.trail_price:,.1f}" if state.armed \
                else f"트레일링 발동까지 ${state.arm_price:,.1f}"
            console.print(f"{now}  가격 ${price:,.1f} ({pnl_pct:+.2f}%)  {tracker}")
            if kind is not None:
                notifier.send(format_exit_alert(kind, price, state))
            if kind in ("stop", "trail"):
                console.print(f"[green]매도 신호({kind}) — 감시 종료[/]")
                state_path.unlink(missing_ok=True)
                return
        except Exception as error:  # noqa: BLE001 - 감시 루프는 멈추면 안 됨
            console.print(f"[red]감시 오류(계속 진행):[/] {error}")
        time.sleep(poll_seconds)
