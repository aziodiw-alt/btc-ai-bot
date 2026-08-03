"""Backward-compatible alias for dashboard history persistence."""

import sys

from btc_terminal.storage import history as _history


# Preserve module-level configuration overrides such as DATABASE_PATH. Importers
# receive the storage module itself, so existing monkeypatching keeps working.
sys.modules[__name__] = _history
