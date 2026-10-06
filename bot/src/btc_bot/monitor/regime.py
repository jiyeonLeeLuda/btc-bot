"""장세(regime) 감시: 가격이 장기선 위/아래냐로 상승/하락장을 판단하고,
상태가 바뀌면(특히 하락장 진입) 알림을 보낸다.

주의: 이건 '하락장이 됐다'를 확인하는 신호다(장기선 교차). '올 것'을 예언하지 않는다.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from btc_bot.data.fetcher import fetch_ohlcv
from btc_bot.notify import Notifier

console = Console()


@dataclass(frozen=True)
class RegimeStatus:
    regime: str      # "up" | "down"
    price: float
    long_ma: float
    gap_pct: float   # (price/long_ma - 1) * 100


def detect_regime(candles, window: int = 200) -> RegimeStatus:
    close = candles["close"]
    long_ma = close.rolling(window).mean().iloc[-1]
    if long_ma != long_ma:  # NaN 체크
        raise ValueError(f"장기선 계산에 캔들이 부족합니다. {window}개 이상 필요")
    price = float(close.iloc[-1])
    return RegimeStatus(
        regime="up" if price >= long_ma else "down",
        price=price,
        long_ma=round(float(long_ma), 2),
        gap_pct=round((price / long_ma - 1) * 100, 2),
    )


def format_alert(status: RegimeStatus, window: int) -> str:
    if status.regime == "down":
        return (
            f"⚠️ 장기 하락장 진입 감지\n"
            f"BTC가 {window}일 평균선 아래로 내려왔어요 "
            f"(현재 ${status.price:,.0f}, {window}일선 ${status.long_ma:,.0f}, "
            f"{status.gap_pct:+.1f}%).\n"
            f"우리 평균회귀 전략은 이런 장에서 손실이 나요 — 매수를 쉬는 걸 권해요."
        )
    return (
        f"✅ 상승장 복귀\n"
        f"BTC가 {window}일 평균선 위로 올라왔어요 "
        f"(현재 ${status.price:,.0f}, {status.gap_pct:+.1f}%)."
    )


def _load_last_regime(state_path: Path) -> str | None:
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text()).get("regime")
    except (json.JSONDecodeError, OSError):
        return None


def _save_regime(state_path: Path, regime: str) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "regime": regime,
        "updated": datetime.now(timezone.utc).isoformat(),
    }))


def run_regime_watch(
    symbol: str,
    window: int,
    state_path: Path,
    notifier: Notifier,
    poll_seconds: int = 3600,
) -> None:
    """주기적으로 장세를 확인하고, 바뀌면 알림. 첫 실행 땐 현재 상태를 한 번 알림.

    알림/네트워크 오류가 루프를 죽이지 않도록 매 반복을 방어한다.
    """
    console.print(f"[bold]장세 감시 시작[/] {symbol} / {window}일선 / {poll_seconds}초마다")
    last = _load_last_regime(state_path)

    while True:
        try:
            candles = fetch_ohlcv(symbol, "1d", limit=window + 50)
            status = detect_regime(candles, window)
            now = datetime.now(timezone.utc).isoformat()
            console.print(
                f"{now}  장세={status.regime}  가격 ${status.price:,.0f}  "
                f"{window}일선 ${status.long_ma:,.0f} ({status.gap_pct:+.1f}%)"
            )
            if status.regime != last:
                notifier.send(format_alert(status, window))
                _save_regime(state_path, status.regime)
                last = status.regime
        except Exception as error:  # noqa: BLE001 - 감시 루프는 멈추면 안 됨
            console.print(f"[red]감시 오류(계속 진행):[/] {error}")
        time.sleep(poll_seconds)
