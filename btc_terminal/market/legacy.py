"""Adapter that preserves calls to the current combined market module."""

from market import get_klines as legacy_get_klines
from market import get_ticker as legacy_get_ticker


class LegacyMarketDataProvider:
    """Bind the existing function API to one normalized exchange name."""

    def __init__(
        self,
        exchange="bybit",
        *,
        ticker_function=legacy_get_ticker,
        klines_function=legacy_get_klines,
    ):
        self.exchange = (
            "okx" if str(exchange).lower() == "okx" else "bybit"
        )
        self._ticker_function = ticker_function
        self._klines_function = klines_function

    def get_ticker(self, symbol=None):
        return self._ticker_function(symbol, exchange=self.exchange)

    def get_klines(self, interval="240", limit=200, symbol=None):
        return self._klines_function(
            interval,
            limit,
            symbol,
            exchange=self.exchange,
        )


__all__ = ["LegacyMarketDataProvider"]
