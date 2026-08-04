"""Backward-compatible public market-data functions."""

from btc_terminal.market.bybit import BybitMarketDataProvider
from btc_terminal.market.binance import BinanceMarketDataProvider
from btc_terminal.market.okx import (
    OkxMarketDataProvider,
    normalize_okx_interval,
    normalize_okx_symbol,
)


def _normalize_exchange(exchange):
    normalized = str(exchange).lower()
    return normalized if normalized in {"bybit", "okx", "binance"} else "bybit"


def _okx_symbol(symbol):
    return normalize_okx_symbol(symbol)


def _okx_interval(interval):
    return normalize_okx_interval(interval)


def _provider(exchange):
    normalized = _normalize_exchange(exchange)
    if normalized == "okx":
        return OkxMarketDataProvider()
    if normalized == "binance":
        return BinanceMarketDataProvider()
    return BybitMarketDataProvider()


def get_ticker(symbol=None, exchange="bybit"):
    """Return a normalized ticker from the selected public exchange."""
    return _provider(exchange).get_ticker(symbol)


def get_klines(interval="240", limit=200, symbol=None, exchange="bybit"):
    """Return normalized ascending candles from the selected exchange."""
    return _provider(exchange).get_klines(interval, limit, symbol)


__all__ = ["get_klines", "get_ticker"]
