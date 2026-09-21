"""Model contract — the single interface every trading algorithm implements.

The same interface is used by the backtester, the paper trader and the live
executor. No copy-paste variants (historical failure #1).
"""
from abc import ABC, abstractmethod
import pandas as pd


class Model(ABC):
    """An algorithm turns candles + portfolio state into an action."""

    name: str = "base"
    version: str = "0.0.1"

    @abstractmethod
    def signal(self, df: pd.DataFrame, state: dict) -> dict:
        """df: OHLCV DataFrame, UTC-indexed, ascending.
        state: {'position': 'long'|'short'|'flat', 'entry': float|None,
                'equity': float}

        Returns dict:
        {
            'action': 'long' | 'short' | 'flat' | 'hold',
            'size':   float | None,   # fraction of equity (None = config default)
            'stop':   float | None,   # price level (None = config default)
            'take':   float | None,
        }
        Deterministic: same inputs -> same output (no hidden state except
        explicitly declared and persisted via save_state/load_state).
        """

    def save_state(self, path: str) -> None:  # optional override
        pass

    def load_state(self, path: str) -> None:  # optional override
        pass
