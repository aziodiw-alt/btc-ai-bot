"""Compatibility facade for the legacy public market-data module."""

from market import get_klines, get_ticker


__all__ = ["get_klines", "get_ticker"]
