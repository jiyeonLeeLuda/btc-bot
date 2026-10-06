import json
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from btc_bot.config import BotConfig
from btc_bot.data.fetcher import fetch_ohlcv
from btc_bot.strategies.base import Strategy

console = Console()


@dataclass(frozen=True)
class PaperAccount:
    cash: float
    btc: float

    def value(self, price: float) -> float:
        return self.cash + self.btc * price


def _buy_all(account: PaperAccount, price: float, fee_rate: float) -> PaperAccount:
    btc_bought = account.cash * (1 - fee_rate) / price
    return replace(account, cash=0.0, btc=account.btc + btc_bought)


def _sell_all(account: PaperAccount, price: float, fee_rate: float) -> PaperAccount:
    cash_received = account.btc * price * (1 - fee_rate)
    return replace(account, cash=account.cash + cash_received, btc=0.0)


def _log_trade(log_path: Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def run_paper_loop(
    strategy: Strategy,
    config: BotConfig,
    log_path: Path,
    poll_seconds: int = 60,
) -> None:
    """Poll Binance, re-evaluate the strategy on the latest candles, simulate fills.

    Runs until Ctrl+C. All trades are appended to a JSONL log.
    """
    account = PaperAccount(cash=config.initial_cash, btc=0.0)
    console.print(f"[bold]페이퍼 트레이딩 시작[/] {config.symbol} / {strategy.name} / 초기자금 ${account.cash:,.0f}")

    try:
        while True:
            candles = fetch_ohlcv(config.symbol, config.timeframe, limit=200)
            price = float(candles["close"].iloc[-1])
            want_long = bool(strategy.generate_signals(candles).iloc[-1] == 1)
            is_long = account.btc > 0

            if want_long and not is_long:
                account = _buy_all(account, price, config.fee_rate)
                action = "BUY"
            elif not want_long and is_long:
                account = _sell_all(account, price, config.fee_rate)
                action = "SELL"
            else:
                action = "HOLD"

            now = datetime.now(timezone.utc).isoformat()
            total = account.value(price)
            console.print(f"{now}  {action:4s}  가격 ${price:,.0f}  평가액 ${total:,.2f}")
            if action != "HOLD":
                _log_trade(log_path, {
                    "time": now, "action": action, "price": price,
                    "cash": account.cash, "btc": account.btc, "value": total,
                })
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        console.print("\n[yellow]종료. 최종 평가액:[/]", f"${account.value(price):,.2f}")
