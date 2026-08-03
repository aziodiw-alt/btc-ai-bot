"""Backward-compatible imports for strategy level calculations."""

from btc_terminal.strategy.levels import (
    calculate_support_resistance,
    calculate_trade_levels,
)


__all__ = ["calculate_support_resistance", "calculate_trade_levels"]
