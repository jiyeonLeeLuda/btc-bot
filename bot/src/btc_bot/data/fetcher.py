"""바이낸스 공개 API로 캔들(OHLCV)을 받아오고 CSV로 저장/로드한다."""

from pathlib import Path

import ccxt
import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume"]


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
    """바이낸스에서 최근 캔들을 받아 datetime 인덱스 DataFrame으로 반환."""
    exchange = ccxt.binance()
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", *COLUMNS])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.set_index("timestamp")


def fetch_last_price(symbol: str) -> float:
    """바이낸스 티커에서 현재가 1개만 받아온다 (가격 감시용 경량 호출)."""
    exchange = ccxt.binance()
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker["last"])


def save_ohlcv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)


def load_ohlcv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 가 없습니다. 먼저 `uv run btc-bot fetch` 로 캔들을 받으세요."
        )
    return pd.read_csv(path, index_col="timestamp", parse_dates=True)
