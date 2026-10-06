from typing import Protocol

import pandas as pd


class Strategy(Protocol):
    """A strategy turns candles into a position signal series.

    Returned series is aligned to the input index, values:
      1 = want to be long, 0 = want to be flat.
    (Spot paper trading — no shorts for now.)
    """

    name: str

    def generate_signals(self, candles: pd.DataFrame) -> pd.Series: ...
