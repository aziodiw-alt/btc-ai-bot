# Package migration boundary

`btc_terminal` is the target namespace for the phased refactor. Creating these
packages does not connect them to production yet. Railway still starts
`launcher.py`; Gunicorn still serves `web/app.py`; Telegram still runs `bot.py`.
The root `app.py`, empty `ai.py`/`report.py`, and fixture `coinglass.py` are
documented legacy modules and are intentionally not removed in this refactor.

The namespace avoids collisions with the existing root files `market.py` and
`strategy.py`. Creating root directories named `market/` or `strategy/` now
could change Python import resolution before any logic has moved.

## Planned ownership

| Package | Intended ownership | Current source modules |
|---|---|---|
| `core` | settings, constants, logging, shared types | `config.py`, launcher environment setup |
| `market` | public/private exchange and sentiment adapters | `market.py`, `sentiment.py`, `okx_client.py`, `bybit_sync.py` |
| `strategy` | profiles, orchestration, grading, levels and risk | `strategy.py`, `fast_strategy.py`, `indicators.py`, `levels.py`, `market_state.py` |
| `storage` | repository interfaces and SQLite implementations | `database.py`, `web/dashboard_history.py`, persistence parts of `web/dashboard_trades.py` |
| `ai` | report orchestration and OpenAI adapter | `ai_report.py`, `web/order_parser.py` |
| `telegram` | Telegram handlers and formatting | `bot.py` |
| `web` | Flask routes and templates | `web/app.py` and presentation assets |
| `application` | shared use-case orchestration and selection | orchestration currently inside `web/app.py` and `bot.py` |

## Migration rule

Move one responsibility at a time. Keep the old import path as a compatibility
wrapper until all consumers and the offline suite have migrated. Never combine
an extraction with changes to thresholds, formulas, schemas, routes, messages,
exchange selection, or cache behavior.

The first compatibility facades intentionally depend from the new namespace to
the legacy modules. This direction is temporary: it makes both import paths
available without changing production. After an implementation moves into the
namespace, the legacy root module will reverse direction and become the wrapper.

## Migration status

- `core.constants`: shared Swing/Fast grade thresholds, Dashboard cache TTLs,
  AI report TTL, and history snapshot interval now have named values; numerical
  values are unchanged.
- `strategy.levels`: implementation moved to
  `btc_terminal.strategy.levels`; root `levels.py` is now the compatibility
  wrapper.
- `strategy.market_state`: implementation moved to
  `btc_terminal.strategy.market_state`; root `market_state.py` is now the
  compatibility wrapper.
- `strategy.indicators`: implementation moved to
  `btc_terminal.strategy.indicators`; root `indicators.py` is now the
  compatibility wrapper.
- `strategy.grading`: pure base grade/decision selection extracted for Swing
  and Fast.
- `strategy.risk`: post-grading RANGE and target-availability gates extracted
  with their current priority and localized decisions.
- `strategy.trend`: EMA-based Swing and Fast trend scoring extracted with the
  current weights and ordered localized explanations.
- `strategy.entry`: distance-based Swing and Fast entry scoring extracted with
  the current thresholds, weights, and ordered explanations.
- `strategy.momentum`: RSI and MACD scoring extracted for both profiles,
  including Fast histogram fallback behavior.
- `strategy.swing` and `strategy.fast`: top-level coordinators moved into the
  namespace; root `strategy.py` and `fast_strategy.py` are compatibility
  wrappers used by existing Dashboard and Telegram imports.
- `application.selection`: strategy, symbol, and exchange normalization moved
  out of Flask; existing web helper names remain wrappers.
- `application.analysis`: strategy dispatch, Swing defaults, snapshot callback,
  and 60-second result cache moved out of Flask. Existing web cache helpers and
  cache objects remain compatibility aliases.
- `application.reports`: AI context loading, report signature, lazy generation,
  and 10-minute cache moved out of Flask; the existing web cache objects remain
  compatibility aliases.
- `application.trades`: persistence-independent sell advice, OKX FIFO, and
  pending-order profit calculations extracted from the dashboard module; legacy
  function imports remain exact aliases.
  Order classification by Swing/Fast zones and targets now uses the same pure
  module as well. Dashboard open-order totals and profit-coverage aggregation
  are also composed there instead of inside the Flask route.
- `storage.history`: dashboard analysis-history SQLite implementation moved out
  of `web`; `dashboard_history` remains an exact module alias so database-path
  overrides, schema upgrades, and existing imports retain their behavior.
- `storage.trades`: trade, execution, and pending-order SQLite repository moved
  out of `web`; both `dashboard_trades` import styles alias the same configurable
  module, preserving the existing database path and schemas.
- `storage.telegram`: stable facade over the root Telegram repository. It uses
  the exact existing functions and leaves `DATABASE_PATH`, `DB_PATH`, and the
  physical `trades.db` location untouched.
- `telegram.formatting`: number, zone, and full strategy-analysis message
  formatting moved out of `bot.py`; the original bot-level names remain exact
  aliases for existing consumers.
- `market.ports`: defines the market-data interface expected by future
  application services.
- `market.legacy`: adapts that interface to the current combined `market.py`
  implementation; production is not switched to it yet.
- `market.bybit` and `market.okx`: separate public-market adapters matching the
  current HTTP parameters and normalized return shapes. Root `market.py` now
  dispatches to these adapters while preserving its function API.
- `market.sentiment`: Bybit derivatives sentiment implementation moved into the
  namespace; root `sentiment.py` is now the compatibility wrapper. It remains
  the sentiment source for both Bybit and OKX analysis.
