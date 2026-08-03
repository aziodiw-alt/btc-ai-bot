# BTC AI Terminal — Handoff

## Current checkpoint

The behavior-preserving architecture refactor is complete through Phases 0–6.
Runtime trading logic, public routes, Telegram behavior, database schemas, cache
TTLs, exchange mappings, and Railway startup behavior were intentionally kept
unchanged.

Baseline at this checkpoint:

- 92 offline tests passing;
- production Python modules compile successfully;
- `ARCHITECTURE.md` contains the real data flow, dependency map, responsibility
  audit, phased plan, current phase status, and legacy-module audit;
- `TESTING.md` documents the safe offline test suite;
- `btc_terminal/README.md` lists the package boundaries and compatibility
  modules introduced during the refactor.

## What moved behind package boundaries

- `btc_terminal.core`: shared constants.
- `btc_terminal.market`: Bybit/OKX adapters, sentiment, ports, and compatibility
  access to current market behavior.
- `btc_terminal.strategy`: Swing/Fast orchestration and extracted grading, risk,
  trend, entry, momentum, indicators, levels, and market-state rules, plus the
  conservative Alpha pullback strategy.
- `btc_terminal.application`: request selection, cached analysis orchestration,
  AI report orchestration, and pure trade/order calculations.
- `btc_terminal.storage`: dashboard history and trade/order repositories, plus a
  safe Telegram storage facade over the unchanged root repository.
- `btc_terminal.telegram`: strategy-analysis message formatting.

Root and `web/` compatibility modules remain in place where existing deployment
or imports depend on them.

## Storage safety

- No database merge or data migration was performed.
- Existing database paths and schemas remain supported.
- Dashboard history and Telegram/trade storage remain physically separate where
  configured that way.
- Do not move or merge live database files as part of an unrelated change.

## Deployment checkpoint

The supported production path is:

```text
railway.json
  -> launcher.py
     -> Gunicorn --chdir web app:app
     -> bot.py
     -> bybit_sync.py (only when credentials are configured)
```

The root `app.py`, empty `ai.py` and `report.py`, and fixture `coinglass.py` are
documented legacy modules. They were not deleted because undocumented manual
users may still exist.

## Verification

From the repository root, use:

```powershell
python run_offline_tests.py
```

In the Codex workspace used for this refactor, third-party packages were kept in
an isolated `work/python_packages` directory and supplied through `PYTHONPATH`.
See `TESTING.md` for details.

Expected result at this checkpoint:

```text
Ran 92 tests
OK
```

Production-module syntax compilation also passed with `python -m compileall`.

## Deliberately deferred

- Physical relocation of tests into `tests/unit`, `tests/integration`, and
  `tests/live`. The safe logical suite is already explicit in
  `run_offline_tests.py`; moving files should be a separate mechanical change.
- Removal of legacy root modules.
- Database consolidation or migration.
- Further scoring changes, additional strategies, or new exchanges.

These should each be handled as separate changes with the 92-test baseline
green before and after.

## Recommended next step

1. Review and commit the current architecture refactor as one checkpoint.
2. Start the next product change in a separate commit.
3. Before editing, run the offline suite and confirm the 92-test baseline.

Suggested checkpoint commit message:

```text
refactor: complete behavior-preserving architecture phases 0-6
```

## Prompt for the next session

```text
Continue BTC AI Terminal from the architecture checkpoint. First read
HANDOFF.md, ARCHITECTURE.md, TESTING.md, and btc_terminal/README.md. Inspect git
status and run run_offline_tests.py before changing code. The expected baseline
is 92 passing tests. Preserve runtime behavior and database compatibility unless
I explicitly request a product-logic change.
```

## Workspace note

The untracked file named `how --stat 992cc51` was present before the refactor
handoff and was intentionally not modified or included in the work.
