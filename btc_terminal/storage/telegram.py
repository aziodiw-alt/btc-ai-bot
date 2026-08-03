"""Stable storage facade over the existing Telegram SQLite repository."""

import database as _legacy


DEFAULT_FEE_RATE = _legacy.DEFAULT_FEE_RATE
init_database = _legacy.init_database
get_open_trade = _legacy.get_open_trade
open_trade = _legacy.open_trade
close_trade = _legacy.close_trade
get_statistics = _legacy.get_statistics
insert_bybit_execution = _legacy.insert_bybit_execution
get_bybit_executions = _legacy.get_bybit_executions
clear_bybit_executions = _legacy.clear_bybit_executions
get_bybit_fifo_statistics = _legacy.get_bybit_fifo_statistics
toggle_signal_subscription = _legacy.toggle_signal_subscription
get_signal_subscribers = _legacy.get_signal_subscribers
set_last_signal_key = _legacy.set_last_signal_key


__all__ = [
    "DEFAULT_FEE_RATE",
    "init_database",
    "get_open_trade",
    "open_trade",
    "close_trade",
    "get_statistics",
    "insert_bybit_execution",
    "get_bybit_executions",
    "clear_bybit_executions",
    "get_bybit_fifo_statistics",
    "toggle_signal_subscription",
    "get_signal_subscribers",
    "set_last_signal_key",
]
