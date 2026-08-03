"""Backward-compatible imports for the Alpha strategy."""

from btc_terminal.strategy.alpha import (
    analyze_alpha_strategy,
    avoid_round_number,
    calculate_alpha_levels,
)


_avoid_round_number = avoid_round_number

__all__ = [
    "_avoid_round_number",
    "analyze_alpha_strategy",
    "avoid_round_number",
    "calculate_alpha_levels",
]
