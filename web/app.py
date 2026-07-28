import os
import sys
import threading
import time
from hmac import compare_digest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from market import get_klines
from strategy import analyze_strategy
from fast_strategy import analyze_fast_strategy
from okx_client import OkxReadOnlyClient
from dashboard_history import (
    get_dashboard_history,
    get_strategy_comparison,
    save_snapshot_if_due,
)
from dashboard_trades import (
    add_pending_orders,
    add_trade,
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

STRATEGY_CACHE_TTL = 60
CANDLE_CACHE_TTL = 15

_strategy_cache = {}
_candle_cache = {}
_cache_lock = threading.Lock()
_ai_cache = {
    "signature": None,
    "created_at": 0.0,
    "value": None,
}
_ai_cache_lock = threading.Lock()


def _unix_seconds(value):
    if isinstance(value, pd.Timestamp):
        return int(value.timestamp())

    numeric_value = int(value)

    if numeric_value > 10_000_000_000:
        return numeric_value // 1000

    return numeric_value


def _normalize_strategy_name(value):
    return "fast" if str(value).lower() == "fast" else "swing"


def _normalize_symbol(value):
    normalized = str(value or "BTCUSDT").replace("/", "").upper()
    return normalized if normalized in SUPPORTED_SYMBOLS else "BTCUSDT"


def _normalize_exchange(value):
    normalized = str(value or "bybit").strip().lower()
    return normalized if normalized in {"bybit", "okx"} else "bybit"


def _get_cached_strategy(strategy_name="swing", symbol="BTCUSDT"):
    strategy_name = _normalize_strategy_name(strategy_name)
    symbol = _normalize_symbol(symbol)
    cache_key = (symbol, strategy_name)
    now = time.monotonic()

    with _cache_lock:
        cached = _strategy_cache.get(cache_key, {})
        cached_value = cached.get("value")
        cache_age = now - cached.get("created_at", 0)

        if cached_value is not None and cache_age < STRATEGY_CACHE_TTL:
            return cached_value

        if strategy_name == "fast":
            result = analyze_fast_strategy(symbol)
        else:
            result = analyze_strategy(symbol)
            result.setdefault("strategy_key", "swing")
            result.setdefault("strategy_name", "Swing")
            result.setdefault(
                "strategy_description",
                "Спокойные сделки · 1D + 4H",
            )
            result.setdefault("trend_max", 40)
            result.setdefault("entry_max", 20)
            result.setdefault("indicators_max", 10)
            result.setdefault("rsi_max", 5)
            result.setdefault("macd_max", 5)
            result.setdefault("sentiment_max", 30)
            result.setdefault("rsi_label", "RSI 4H")

        save_snapshot_if_due(result)
        _strategy_cache[cache_key] = {
            "value": result,
            "created_at": time.monotonic(),
        }
        return result


def _get_cached_candles(timeframe, symbol="BTCUSDT"):
    symbol = _normalize_symbol(symbol)
    cache_key = (symbol, timeframe)
    now = time.monotonic()

    with _cache_lock:
        cached = _candle_cache.get(cache_key)

        if cached and now - cached["created_at"] < CANDLE_CACHE_TTL:
            return cached["value"]

        frame = get_klines(timeframe, 250, symbol)
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
        result = _get_cached_strategy(strategy_name, symbol)
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

    if active_exchange == "okx":
        try:
            okx_client = OkxReadOnlyClient()
            okx_account = okx_client.connection_status()
            okx_open_orders = okx_client.get_open_orders()
            okx_trade_history = okx_client.get_trade_history()
        except Exception as exc:
            okx_account_error = str(exc)

    try:
        current_price = result["price"] if result else None
        if has_unassigned_orders(symbol):
            strategy_levels = {
                "swing": _get_cached_strategy("swing", symbol),
                "fast": _get_cached_strategy("fast", symbol),
            }
            classify_unassigned_orders(strategy_levels, symbol)
        trades_data = get_trades(current_price, symbol=symbol)
        open_orders = [
            order
            for order in get_pending_orders(
                current_price,
                symbol=symbol,
            )
            if order["status"] == "OPEN"
        ]
        expected_profit = sum(
            float(order["estimated_profit_usdt"])
            for order in open_orders
            if order["estimated_profit_usdt"] is not None
        )
        expected_cost = sum(
            float(order["estimated_cost_usdt"])
            for order in open_orders
            if order["estimated_cost_usdt"] is not None
        )
        open_order_summary = {
            "count": len(open_orders),
            "buy_count": sum(
                order["side"] == "BUY" for order in open_orders
            ),
            "sell_count": sum(
                order["side"] == "SELL" for order in open_orders
            ),
            "buy_value": sum(
                float(order["order_value"])
                for order in open_orders
                if order["side"] == "BUY"
            ),
            "sell_value": sum(
                float(order["order_value"])
                for order in open_orders
                if order["side"] == "SELL"
            ),
            "expected_profit": expected_profit,
            "expected_profit_pct": (
                expected_profit / expected_cost * 100
                if expected_cost > 0
                else None
            ),
            "calculated_sell_count": sum(
                order["estimated_profit_usdt"] is not None
                for order in open_orders
                if order["side"] == "SELL"
            ),
        }
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
        candles = _get_cached_candles(requested_timeframe, symbol)
        result = _get_cached_strategy(strategy_name, symbol)

        return jsonify(
            {
                "candles": candles,
                "symbol": symbol,
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


@app.route("/api/ai-report", methods=["POST"])
def ai_report():
    try:
        symbol = _normalize_symbol(
            request.args.get("symbol", "BTCUSDT")
        )
        strategy_name = _normalize_strategy_name(
            request.args.get("strategy", "swing")
        )
        result = _get_cached_strategy(strategy_name, symbol)

        with ThreadPoolExecutor(max_workers=2) as executor:
            whale_future = executor.submit(get_whale_context)
            news_future = executor.submit(get_news_context)
            whale_context = whale_future.result()
            news_context = news_future.result()

        signature = (
            strategy_name,
            symbol,
            result.get("price"),
            result.get("total_score"),
            result.get("grade"),
            result.get("decision"),
            whale_context.get("score"),
            tuple(
                event.get("url")
                for event in whale_context.get("events", [])[:3]
            ),
            news_context.get("score"),
            tuple(
                article.get("url")
                for article in news_context.get("articles", [])[:3]
            ),
        )
        now = time.monotonic()

        with _ai_cache_lock:
            if (
                _ai_cache["value"] is not None
                and _ai_cache["signature"] == signature
                and now - _ai_cache["created_at"] < 600
            ):
                return jsonify(
                    {
                        "report": _ai_cache["value"],
                        "cached": True,
                    }
                )

        from ai_report import generate_report

        report = generate_report(
            result,
            whale_context=whale_context,
            news_context=news_context,
        )

        with _ai_cache_lock:
            _ai_cache["signature"] = signature
            _ai_cache["created_at"] = time.monotonic()
            _ai_cache["value"] = report

        return jsonify(
            {
                "report": report,
                "cached": False,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True)
