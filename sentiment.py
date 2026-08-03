"""Backward-compatible imports for Bybit derivatives sentiment."""

from btc_terminal.market.sentiment import (
    get_funding,
    get_long_short,
    get_open_interest,
    get_sentiment,
)


__all__ = [
    "get_funding",
    "get_long_short",
    "get_open_interest",
    "get_sentiment",
]
