import os
import sys
import time
from hmac import compare_digest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from market import get_klines, get_ticker
from strategy import analyze_strategy
from fast_strategy import analyze_fast_strategy
from alpha_strategy import analyze_alpha_strategy
from okx_client import OkxReadOnlyClient
from dashboard_history import (
    get_dashboard_history,
    get_strategy_comparison,
    save_snapshot_if_due,
)
from dashboard_trades import (
    add_pending_orders,
    add_trade,
    add_okx_order_profit_estimates,
    calculate_okx_fifo_statistics,
    calculate_sell_advice,
    cancel_pending_order,
    classify_unassigned_orders,
    fill_pending_order,
    get_pending_orders,
    get_trades,
    has_unassigned_orders,
    import_bybit_csv,
)
from order_parser import parse_orders
from whale_alert import get_whale_context
from crypto_news import get_news_context
from btc_terminal.core.constants import (
    CANDLE_CACHE_TTL_SECONDS,
    STRATEGY_CACHE_TTL_SECONDS,
)
from btc_terminal.application.selection import (
    normalize_exchange,
    normalize_strategy_name,
    normalize_symbol,
)
from btc_terminal.application.analysis import AnalysisService
from btc_terminal.application.reports import AIReportService
from btc_terminal.application.trades import summarize_open_orders
from btc_terminal.application.rescue import calculate_rescue_plan


app = Flask(__name__)
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
SUPPORTED_SYMBOLS = {
    "BTCUSDT": {
        "symbol": "BTCUSDT",
        "display": "BTC/USDT",
        "asset": "BTC",
        "name": "Bitcoin",
        "icon": "₿",
    },
    "ETHUSDT": {
        "symbol": "ETHUSDT",
        "display": "ETH/USDT",
        "asset": "ETH",
        "name": "Ethereum",
        "icon": "Ξ",
    },
}
DISPLAY_TIMEZONE = ZoneInfo(
    os.getenv("DASHBOARD_TIMEZONE", "Europe/Copenhagen")
)


@app.before_request
def require_dashboard_login():
    if request.endpoint == "health":
        return None

    if not DASHBOARD_USERNAME or not DASHBOARD_PASSWORD:
        return Response(
            "Dashboard login is not configured.",
            status=503,
        )

    authorization = request.authorization
    valid_login = (
        authorization is not None
        and compare_digest(
            authorization.username or "",
            DASHBOARD_USERNAME,
        )
        and compare_digest(
            authorization.password or "",
            DASHBOARD_PASSWORD,
        )
    )

    if valid_login:
        return None

    return Response(
        "Authentication required.",
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="Trading Dashboard"'},
    )


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/api/okx/status")
def okx_status():
    try:
        status = OkxReadOnlyClient().connection_status()
        return jsonify(status)
    except Exception as error:
        return jsonify(
            {
                "connected": False,
                "error": str(error),
            }
        ), 502


@app.template_filter("local_datetime")
def local_datetime(value):
    if not value:
        return "—"

    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(DISPLAY_TIMEZONE)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value).replace("T", " ")

STRATEGY_CACHE_TTL = STRATEGY_CACHE_TTL_SECONDS
CANDLE_CACHE_TTL = CANDLE_CACHE_TTL_SECONDS

_candle_cache = {}
_analysis_service = AnalysisService(
    analyze_strategy,
    analyze_fast_strategy,
    save_snapshot_if_due,
    alpha_analyzer=analyze_alpha_strategy,
    cache_ttl=STRATEGY_CACHE_TTL,
)
_strategy_cache = _analysis_service.cache
_cache_lock = _analysis_service.lock
def _load_report_generator():
    from ai_report import generate_report

    return generate_report


def _unix_seconds(value):
    if isinstance(value, pd.Timestamp):
        return int(value.timestamp())

    numeric_value = int(value)

    if numeric_value > 10_000_000_000:
        return numeric_value // 1000

    return numeric_value


def _normalize_strategy_name(value):
    return normalize_strategy_name(value)


def _normalize_symbol(value):
    return normalize_symbol(value)


def _normalize_exchange(value):
    return normalize_exchange(value)


def _get_cached_strategy(
    strategy_name="swing",
    symbol="BTCUSDT",
    exchange="bybit",
):
    return _analysis_service.analyze(strategy_name, symbol, exchange)


_ai_report_service = AIReportService(
    _get_cached_strategy,
    get_whale_context,
    get_news_context,
    _load_report_generator,
)
_ai_cache = _ai_report_service.cache
_ai_cache_lock = _ai_report_service.lock


def _get_cached_candles(
    timeframe,
    symbol="BTCUSDT",
    exchange="bybit",
):
    symbol = _normalize_symbol(symbol)
    exchange = _normalize_exchange(exchange)
    cache_key = (exchange, symbol, timeframe)
    now = time.monotonic()

    with _cache_lock:
        cached = _candle_cache.get(cache_key)

        if cached and now - cached["created_at"] < CANDLE_CACHE_TTL:
            return cached["value"]

        frame = get_klines(
            timeframe,
            250,
            symbol,
            exchange=exchange,
        )
        candles = [
            {
                "time": _unix_seconds(row.time),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
            }
            for row in frame.itertuples(index=False)
        ]

        _candle_cache[cache_key] = {
            "created_at": time.monotonic(),
            "value": candles,
        }
        return candles


@app.route("/")
def home():
    symbol = _normalize_symbol(request.args.get("symbol", "BTCUSDT"))
    active_exchange = _normalize_exchange(
        request.args.get("exchange", "bybit")
    )
    asset_info = SUPPORTED_SYMBOLS[symbol]
    strategy_name = _normalize_strategy_name(
        request.args.get("strategy", "swing")
    )
    try:
        result = _get_cached_strategy(
            strategy_name,
            symbol,
            active_exchange,
        )
        history_data = get_dashboard_history(
            strategy_name=strategy_name,
            symbol=asset_info["display"],
        )
        strategy_comparison = get_strategy_comparison(
            symbol=asset_info["display"]
        )
        error = None
    except Exception as exc:
        result = None
        history_data = {
            "items": [],
            "stats": {
                "total": 0,
                "average_score": 0,
                "buy_count": 0,
                "wait_count": 0,
                "skip_count": 0,
            },
        }
        strategy_comparison = []
        error = str(exc)

    trades_data = {
        "items": [],
        "executions": [],
        "cycles": [],
        "bybit": {
            "execution_count": 0,
            "closed_count": 0,
            "wins": 0,
            "total_net_pnl": 0,
            "open_quantity": 0,
            "open_cost": 0,
            "unmatched_sell_quantity": 0,
        },
        "stats": {
            "total": 0,
            "open_count": 0,
            "closed_count": 0,
            "open_value_usdt": 0,
            "closed_profit_usdt": 0,
            "win_rate": 0,
        },
    }
    trade_data_error = None
    okx_account = None
    okx_account_error = None
    okx_open_orders = []
    okx_trade_history = []
    sell_advice = {
        "available": False,
        "reason": "Нет данных для расчёта.",
    }

    if active_exchange == "okx":
        try:
            okx_client = OkxReadOnlyClient()
            okx_account = okx_client.connection_status()
            okx_open_orders = okx_client.get_open_orders()
            okx_trade_history = okx_client.get_trade_history()

            okx_instrument = (
                f"{asset_info['asset']}-USDC"
            )
            okx_fifo = calculate_okx_fifo_statistics(
                okx_trade_history,
                okx_instrument,
            )
            okx_open_orders = add_okx_order_profit_estimates(
                okx_open_orders,
                okx_fifo,
            )
            pending_okx_sell_quantity = sum(
                float(order.get("remaining_size") or 0)
                for order in okx_open_orders
                if order.get("side") == "SELL"
                and order.get("instrument") == okx_instrument
            )
            sell_advice = calculate_sell_advice(
                okx_fifo,
                current_price=result["price"] if result else None,
                pending_sell_quantity=pending_okx_sell_quantity,
                quote_currency="USDC",
            )
        except Exception as exc:
            okx_account_error = str(exc)

    try:
        current_price = result["price"] if result else None
        if has_unassigned_orders(symbol):
            strategy_levels = {
                "swing": _get_cached_strategy("swing", symbol),
                "fast": _get_cached_strategy("fast", symbol),
                "alpha": _get_cached_strategy("alpha", symbol),
            }
            classify_unassigned_orders(strategy_levels, symbol)
        trades_data = get_trades(current_price, symbol=symbol)
        open_orders, open_order_summary = summarize_open_orders(
            get_pending_orders(current_price, symbol=symbol)
        )
        sell_quantity = sum(
            float(order["order_quantity"])
            for order in open_orders
            if order["side"] == "SELL"
        )
        if active_exchange == "bybit":
            sell_advice = calculate_sell_advice(
                trades_data["bybit"],
                current_price=current_price,
                pending_sell_quantity=sell_quantity,
                quote_currency="USDT",
            )
        trades_data["stats"]["open_count"] = len(open_orders)
    except Exception as exc:
        trade_data_error = str(exc)
        open_orders = []
        open_order_summary = {
            "count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "buy_value": 0,
            "sell_value": 0,
            "expected_profit": 0,
            "expected_profit_pct": None,
            "profit_coverage_pct": None,
            "profit_is_complete": False,
            "matched_sell_quantity": 0,
            "unmatched_sell_quantity": 0,
            "calculated_sell_count": 0,
        }

    return render_template(
        "index.html",
        result=result,
        active_symbol=symbol,
        active_exchange=active_exchange,
        asset_info=asset_info,
        supported_symbols=SUPPORTED_SYMBOLS.values(),
        active_strategy=strategy_name,
        history=history_data["items"],
        stats=history_data["stats"],
        strategy_comparison=strategy_comparison,
        trades=trades_data["items"],
        bybit_executions=trades_data["executions"],
        bybit_cycles=trades_data["cycles"],
        bybit_stats=trades_data["bybit"],
        trade_stats=trades_data["stats"],
        open_orders=open_orders,
        open_order_summary=open_order_summary,
        sell_advice=sell_advice,
        default_trade_date=datetime.now().strftime("%Y-%m-%dT%H:%M"),
        trade_added=request.args.get("trade_added") == "1",
        trade_error=request.args.get("trade_error"),
        csv_added=request.args.get("csv_added"),
        csv_duplicates=request.args.get("csv_duplicates"),
        csv_ignored=request.args.get("csv_ignored"),
        csv_error=request.args.get("csv_error"),
        order_filled=request.args.get("order_filled") == "1",
        order_cancelled=request.args.get("order_cancelled") == "1",
        order_fill_error=request.args.get("order_fill_error"),
        trade_data_error=trade_data_error,
        okx_account=okx_account,
        okx_account_error=okx_account_error,
        okx_open_orders=okx_open_orders,
        okx_trade_history=okx_trade_history,
        error=error,
    )


@app.route("/trades", methods=["POST"])
def create_trade():
    try:
        symbol = _normalize_symbol(request.form.get("symbol", "BTCUSDT"))
        add_trade(
            entry_price=request.form.get("entry_price"),
            amount_usdt=request.form.get("amount_usdt"),
            trade_date=request.form.get("trade_date"),
            status=request.form.get("status", "OPEN"),
            sell_price=request.form.get("sell_price"),
            notes=request.form.get("notes", ""),
            symbol=symbol,
        )
        return redirect(
            url_for("home", symbol=symbol, trade_added="1") + "#trades"
        )
    except (TypeError, ValueError) as exc:
        return redirect(
            url_for(
                "home",
                symbol=request.form.get("symbol", "BTCUSDT"),
                trade_error=str(exc),
            )
            + "#trades"
        )


@app.route("/trades/import-csv", methods=["POST"])
def import_trades_csv():
    try:
        symbol = _normalize_symbol(request.form.get("symbol", "BTCUSDT"))
        report = import_bybit_csv(
            request.files.get("csv_file"),
            symbol=symbol,
        )
        return redirect(
            url_for(
                "home",
                symbol=symbol,
                csv_added=report["added"],
                csv_duplicates=report["duplicates"],
                csv_ignored=report["ignored"],
            )
            + "#trades"
        )
    except (TypeError, ValueError) as exc:
        return redirect(
            url_for("home", csv_error=str(exc)) + "#trades"
        )


@app.route("/orders")
def orders_page():
    symbol = _normalize_symbol(request.args.get("symbol", "BTCUSDT"))
    try:
        if has_unassigned_orders(symbol):
            strategy_levels = {
                "swing": _get_cached_strategy("swing", symbol),
                "fast": _get_cached_strategy("fast", symbol),
                "alpha": _get_cached_strategy("alpha", symbol),
            }
            classify_unassigned_orders(strategy_levels, symbol)
        orders = get_pending_orders(symbol=symbol)
        orders_error = None
    except Exception as exc:
        orders = []
        orders_error = str(exc)

    return render_template(
        "orders.html",
        orders=orders,
        active_symbol=symbol,
        asset_info=SUPPORTED_SYMBOLS[symbol],
        orders_error=orders_error,
        order_saved=request.args.get("saved"),
        order_duplicates=request.args.get("duplicates"),
        order_error=request.args.get("error"),
    )


@app.route("/orders/parse", methods=["POST"])
def parse_order_input():
    try:
        orders = parse_orders(
            image_file=request.files.get("order_image"),
            copied_text=request.form.get("copied_text", ""),
        )
        return render_template(
            "order_review.html",
            orders=orders,
            parse_error=None,
        )
    except Exception as exc:
        return render_template(
            "order_review.html",
            orders=[],
            parse_error=str(exc),
        )


@app.route("/orders/save", methods=["POST"])
def save_orders():
    try:
        count = int(request.form.get("order_count", "0"))
        orders = []

        for index in range(count):
            orders.append(
                {
                    "symbol": request.form.get(f"symbol_{index}"),
                    "side": request.form.get(f"side_{index}"),
                    "order_type": request.form.get(f"order_type_{index}"),
                    "order_value": request.form.get(f"order_value_{index}"),
                    "order_price": request.form.get(f"order_price_{index}"),
                    "order_quantity": request.form.get(
                        f"order_quantity_{index}"
                    ),
                    "created_at": request.form.get(f"created_at_{index}"),
                    "order_id": request.form.get(f"order_id_{index}"),
                }
            )

        symbol = _normalize_symbol(
            orders[0].get("symbol") if orders else "BTCUSDT"
        )
        strategy_levels = {
            "swing": _get_cached_strategy("swing", symbol),
            "fast": _get_cached_strategy("fast", symbol),
            "alpha": _get_cached_strategy("alpha", symbol),
        }
        report = add_pending_orders(
            orders,
            strategy_levels=strategy_levels,
        )
        return redirect(
            url_for(
                "orders_page",
                symbol=symbol,
                saved=report["saved"],
                duplicates=report["duplicates"],
            )
        )
    except (TypeError, ValueError) as exc:
        return redirect(url_for("orders_page", error=str(exc)))


@app.route("/orders/<int:order_id>/fill", methods=["POST"])
def fill_order(order_id):
    try:
        fill_pending_order(order_id)
        symbol = _normalize_symbol(request.args.get("symbol", "BTCUSDT"))
        strategy_name = _normalize_strategy_name(
            request.args.get("strategy", "swing")
        )
        return redirect(
            url_for(
                "home",
                symbol=symbol,
                strategy=strategy_name,
                order_filled="1",
            )
            + "#open-orders"
        )
    except (TypeError, ValueError) as exc:
        symbol = _normalize_symbol(request.args.get("symbol", "BTCUSDT"))
        strategy_name = _normalize_strategy_name(
            request.args.get("strategy", "swing")
        )
        return redirect(
            url_for(
                "home",
                symbol=symbol,
                strategy=strategy_name,
                order_fill_error=str(exc),
            )
            + "#open-orders"
        )


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    symbol = _normalize_symbol(request.args.get("symbol", "BTCUSDT"))
    strategy_name = _normalize_strategy_name(
        request.args.get("strategy", "swing")
    )

    try:
        cancel_pending_order(order_id)
        return redirect(
            url_for(
                "home",
                symbol=symbol,
                strategy=strategy_name,
                order_cancelled="1",
            )
            + "#open-orders"
        )
    except (TypeError, ValueError) as exc:
        return redirect(
            url_for(
                "home",
                symbol=symbol,
                strategy=strategy_name,
                order_fill_error=str(exc),
            )
            + "#open-orders"
        )


@app.route("/api/chart-data")
def chart_data():
    try:
        symbol = _normalize_symbol(
            request.args.get("symbol", "BTCUSDT")
        )
        requested_timeframe = request.args.get("timeframe", "240")
        allowed_timeframes = {
            "60": "1H",
            "240": "4H",
            "D": "1D",
        }

        if requested_timeframe not in allowed_timeframes:
            return jsonify({"error": "Неподдерживаемый таймфрейм"}), 400

        strategy_name = _normalize_strategy_name(
            request.args.get("strategy", "swing")
        )
        exchange = _normalize_exchange(
            request.args.get("exchange", "bybit")
        )
        candles = _get_cached_candles(
            requested_timeframe,
            symbol,
            exchange,
        )
        result = _get_cached_strategy(
            strategy_name,
            symbol,
            exchange,
        )

        return jsonify(
            {
                "candles": candles,
                "symbol": symbol,
                "exchange": exchange,
                "display_symbol": (
                    symbol.replace("USDT", "/USD (USDC)")
                    if exchange == "okx"
                    else symbol.replace("USDT", "/USDT")
                ),
                "timeframe": requested_timeframe,
                "timeframe_label": allowed_timeframes[requested_timeframe],
                "levels": {
                    "current_price": result["price"],
                    "support": result["support"],
                    "support_zone": result.get("support_zone"),
                    "resistance": result["resistance"],
                    "buy_zone_1": result["buy_zone_1"],
                    "buy_zone_2": result["buy_zone_2"],
                    "stop_loss": result["stop_loss"],
                    "take_profit_1": result["take_profit_1"],
                    "take_profit_2": result["take_profit_2"],
                },
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/whale-alerts")
def whale_alerts():
    return jsonify(get_whale_context())


@app.route("/api/crypto-news")
def crypto_news():
    return jsonify(get_news_context())


@app.route("/api/alpha-rescue", methods=["POST"])
def alpha_rescue():
    try:
        payload = request.get_json(silent=True) or {}
        exchange = _normalize_exchange(payload.get("exchange", "bybit"))
        base_asset = str(payload.get("base_asset", "BTC")).upper()
        btc_price = float(get_ticker("BTCUSDT", exchange=exchange)["price"])
        eth_price = float(get_ticker("ETHUSDT", exchange=exchange)["price"])
        cross_price = eth_price / btc_price
        base_usd_price = btc_price if base_asset == "BTC" else eth_price
        result = calculate_rescue_plan(
            base_asset,
            payload.get("base_quantity"),
            cross_price,
            cross_exit_price=payload.get("cross_exit_price"),
            fee_rate=payload.get("fee_rate", 0.001),
            minimum_net_gain_pct=payload.get("minimum_net_gain_pct", 1.0),
            base_usd_price=base_usd_price,
            average_cost_usd=payload.get("average_cost_usd"),
        )
        result["exchange"] = exchange
        return jsonify(result)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/ai-report", methods=["POST"])
def ai_report():
    try:
        symbol = _normalize_symbol(
            request.args.get("symbol", "BTCUSDT")
        )
        strategy_name = _normalize_strategy_name(
            request.args.get("strategy", "swing")
        )
        return jsonify(_ai_report_service.generate(strategy_name, symbol))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True)
