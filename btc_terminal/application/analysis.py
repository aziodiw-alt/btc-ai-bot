"""Cached strategy-selection use case shared by delivery adapters."""

import threading
import time

from btc_terminal.application.selection import (
    normalize_exchange,
    normalize_strategy_name,
    normalize_symbol,
)
from btc_terminal.core.constants import STRATEGY_CACHE_TTL_SECONDS


class AnalysisService:
    def __init__(
        self,
        swing_analyzer,
        fast_analyzer,
        snapshot_callback,
        *,
        alpha_analyzer=None,
        cache_ttl=STRATEGY_CACHE_TTL_SECONDS,
        clock=time.monotonic,
    ):
        self.swing_analyzer = swing_analyzer
        self.fast_analyzer = fast_analyzer
        self.alpha_analyzer = alpha_analyzer
        self.snapshot_callback = snapshot_callback
        self.cache_ttl = cache_ttl
        self.clock = clock
        self.cache = {}
        self.lock = threading.Lock()

    def analyze(self, strategy_name="swing", symbol="BTCUSDT", exchange="bybit"):
        strategy_name = normalize_strategy_name(strategy_name)
        symbol = normalize_symbol(symbol)
        exchange = normalize_exchange(exchange)
        cache_key = (exchange, symbol, strategy_name)
        now = self.clock()

        with self.lock:
            cached = self.cache.get(cache_key, {})
            cached_value = cached.get("value")
            cache_age = now - cached.get("created_at", 0)
            if cached_value is not None and cache_age < self.cache_ttl:
                return cached_value

            if strategy_name == "fast":
                result = self.fast_analyzer(symbol, exchange=exchange)
            elif strategy_name == "alpha" and self.alpha_analyzer is not None:
                result = self.alpha_analyzer(symbol, exchange=exchange)
            else:
                result = self.swing_analyzer(symbol, exchange=exchange)
                self._add_swing_defaults(result)

            self.snapshot_callback(result)
            self.cache[cache_key] = {
                "value": result,
                "created_at": self.clock(),
            }
            return result

    @staticmethod
    def _add_swing_defaults(result):
        result.setdefault("strategy_key", "swing")
        result.setdefault("strategy_name", "Swing")
        result.setdefault(
            "strategy_description",
            "Спокойные сделки · 1D + 4H",
        )
        result.setdefault("trend_max", 40)
        result.setdefault("entry_max", 20)
        result.setdefault("indicators_max", 10)
        result.setdefault("rsi_max", 5)
        result.setdefault("macd_max", 5)
        result.setdefault("sentiment_max", 30)
        result.setdefault("rsi_label", "RSI 4H")


__all__ = ["AnalysisService"]
