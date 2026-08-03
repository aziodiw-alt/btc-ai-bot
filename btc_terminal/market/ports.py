"""Interfaces consumed by application and strategy services."""

from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    """Provide normalized ticker and candle data for one exchange."""

    def get_ticker(self, symbol=None):
        """Return price, 24-hour high/low, and volume."""

    def get_klines(self, interval="240", limit=200, symbol=None) -> pd.DataFrame:
        """Return ascending OHLCV candles in the legacy DataFrame shape."""


__all__ = ["MarketDataProvider"]
