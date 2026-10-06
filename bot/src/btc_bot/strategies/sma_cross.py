from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SmaCross:
    """Long when fast SMA is above slow SMA, flat otherwise."""

    fast: int = 20
    slow: int = 60

    @property
    def name(self) -> str:
        return f"sma_cross({self.fast},{self.slow})"

    def generate_signals(self, candles: pd.DataFrame) -> pd.Series:
        if self.fast >= self.slow:
            raise ValueError("fast 기간은 slow보다 짧아야 합니다")
        close = candles["close"]
        fast_sma = close.rolling(self.fast).mean()
        slow_sma = close.rolling(self.slow).mean()
        signal = (fast_sma > slow_sma).astype(int)
        # SMA가 아직 계산되지 않은 초반 구간은 포지션 없음
        return signal.where(slow_sma.notna(), 0)
