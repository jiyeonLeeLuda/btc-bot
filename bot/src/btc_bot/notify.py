"""매매 알림. 지금은 디스코드 웹훅 + '채널 없음(NullNotifier)' 폴백.

핵심 원칙: 알림 전송 실패가 **절대** 트레이딩 루프를 죽이면 안 된다.
모든 전송 오류는 삼키고 콘솔 경고만 남긴다.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Protocol


class Notifier(Protocol):
    def send(self, message: str) -> None: ...


class NullNotifier:
    """알림 채널 미설정 시 — 아무것도 하지 않는다."""

    def send(self, message: str) -> None:
        return None


class DiscordNotifier:
    """디스코드 웹훅으로 메시지를 보낸다.

    _post를 주입하면 네트워크 없이 테스트할 수 있다(의존성 역전).
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 5.0,
        post: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._url = webhook_url
        self._timeout = timeout
        self._post = post or self._http_post

    def send(self, message: str) -> None:
        try:
            self._post(self._url, {"content": message})
        except Exception as error:  # noqa: BLE001 - 알림 실패는 루프를 멈추면 안 됨
            print(f"[알림 전송 실패] {error}")

    def _http_post(self, url: str, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=self._timeout)


def make_notifier() -> Notifier:
    """환경변수 BTC_BOT_DISCORD_WEBHOOK가 있으면 디스코드, 없으면 Null."""
    url = os.environ.get("BTC_BOT_DISCORD_WEBHOOK", "").strip()
    return DiscordNotifier(url) if url else NullNotifier()
