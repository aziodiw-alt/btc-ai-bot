"""Normalize user-selected analysis dimensions."""


SUPPORTED_ANALYSIS_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})


def normalize_strategy_name(value):
    normalized = str(value or "swing").strip().lower()
    return normalized if normalized in {"swing", "fast", "alpha"} else "swing"


def normalize_symbol(value):
    normalized = str(value or "BTCUSDT").replace("/", "").upper()
    return (
        normalized
        if normalized in SUPPORTED_ANALYSIS_SYMBOLS
        else "BTCUSDT"
    )


def normalize_exchange(value):
    normalized = str(value or "bybit").strip().lower()
    return normalized if normalized in {"bybit", "okx", "binance"} else "bybit"


__all__ = [
    "SUPPORTED_ANALYSIS_SYMBOLS",
    "normalize_exchange",
    "normalize_strategy_name",
    "normalize_symbol",
]
