# Testing BTC AI Terminal

## Deterministic offline suite

Run:

```powershell
python run_offline_tests.py
```

This suite does not call Bybit, OKX, OpenAI, Telegram, news feeds, or whale
feeds. It covers strategy contracts, grading boundaries, Telegram formatting,
Dashboard authentication/API/cache behavior, SQLite schemas, market state,
levels, OKX response normalization, pending-order profit, FIFO calculations,
and sell advice.

The offline module list is explicit in `run_offline_tests.py`. Do not replace
this command with unrestricted `unittest discover` yet: several historical
files named `test_*.py` execute live requests at import time.

## Live/manual checks

The following files are diagnostic scripts, not deterministic unit tests:

- `test_ai_report.py` — calls OpenAI and requires `OPENAI_API_KEY`.
- `test_coinglass.py` and `test_coinglass_module.py` — legacy sentiment checks.
- `test_config.py` — prints environment configuration status.
- `test_filter.py` — fetches live market data.
- `test_indicators.py` — fetches live candles.
- `test_klines.py` and `test_market.py` — call public exchange APIs.

Run any of these individually and intentionally. They must not be part of CI or
the default offline regression gate until rewritten with mocks.

## Refactoring gate

Before and after every behavior-preserving refactoring phase:

1. Run `python run_offline_tests.py`.
2. Confirm that the same number of tests passes.
3. Add a regression test before fixing any newly discovered behavior bug.
4. Keep live API checks separate from the offline result.
# Current baseline

The behavior-preserving architecture refactor baseline is **87 passing offline
tests**, plus successful syntax compilation of the production Python modules.
