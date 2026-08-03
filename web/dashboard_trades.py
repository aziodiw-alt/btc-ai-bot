"""Backward-compatible alias for trade and order persistence."""

import sys

from btc_terminal.storage import trades as _trades


# Existing web, Telegram, sync, and test imports share one configurable module.
sys.modules[__name__] = _trades
