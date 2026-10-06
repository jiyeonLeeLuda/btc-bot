from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    # Binance spot taker fee (0.1%). Paper trading applies this on every fill.
    fee_rate: float = 0.001
    initial_cash: float = 10_000.0


DEFAULT_CONFIG = BotConfig()
