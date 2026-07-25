import asyncio
import json
import os
import tempfile

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai_report import generate_report
from database import (
    clear_bybit_executions,
    close_trade,
    get_bybit_fifo_statistics,
    get_open_trade,
    get_signal_subscribers,
    get_statistics,
    init_database,
    open_trade,
    set_last_signal_key,
    toggle_signal_subscription,
)
from market import get_ticker
from strategy import analyze_strategy
from trade_import import import_bybit_csv
from web.dashboard_trades import get_pending_orders, get_trades


load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "").strip()

keyboard = ReplyKeyboardMarkup(
    [
        ["📊 Анализ BTC", "📊 Анализ ETH"],
        ["📋 Открытые ордера", "📈 Статистика"],
        ["🌐 Открыть Dashboard"],
        ["🔔 Автосигналы ВКЛ/ВЫКЛ"],
    ],
    resize_keyboard=True,
)


def format_number(value, decimals=0):
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", " ")


def format_zone(zone):
    if isinstance(zone, (list, tuple)) and len(zone) == 2:
        low, high = sorted(zone)
        return f"{format_number(low)} – {format_number(high)}"
    return str(zone)


def format_analysis(result):
    display_symbol = result.get("display_symbol", "BTC/USDT")
    price_decimals = 2 if display_symbol.startswith("ETH") else 0
    reasons = "\n".join(f"• {item}" for item in result.get("reasons", []))
    warnings = "\n".join(f"• {item}" for item in result.get("warnings", []))

    return f"""📊 {display_symbol}

💰 Цена: {format_number(result["price"], price_decimals)}

📈 Trend: {result["trend_score"]}/40
🎯 Entry: {result["entry_score"]}/20
📊 Indicators: {result["indicators_score"]}/10
🌍 Sentiment: {result["sentiment_score"]}/30

🏆 Итог: {result["total_score"]}/100
⭐ Grade: {result["grade"]}

🤖 Решение:
{result["decision"]}

🎯 Buy Zone 1: {format_zone(result["buy_zone_1"])}
🎯 Buy Zone 2: {format_zone(result["buy_zone_2"])}
🛑 Stop Loss: {format_number(result["stop_loss"])}
💰 Take Profit 1: {format_number(result["take_profit_1"])}
🚀 Take Profit 2: {format_number(result["take_profit_2"])}

✅ Причины:
{reasons or "• Нет"}

⚠️ Предупреждения:
{warnings or "• Нет"}"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_buy_amount", None)
    context.user_data.pop("awaiting_clear_csv_confirmation", None)
    await update.message.reply_text(
        "Привет! Выбери действие:",
        reply_markup=keyboard,
    )


async def analyze_asset(update, symbol):
    display_symbol = symbol.replace("USDT", "/USDT")
    await update.message.reply_text(
        f"Получаю данные {display_symbol} с Bybit и считаю индикаторы... ⏳"
    )
    result = await asyncio.to_thread(analyze_strategy, symbol)
    await update.message.reply_text(format_analysis(result), reply_markup=keyboard)

    await update.message.reply_text("Готовлю AI-комментарий... 🤖")
    ai_text = await asyncio.to_thread(generate_report, result)
    await update.message.reply_text(
        f"🤖 AI-комментарий:\n\n{ai_text}",
        reply_markup=keyboard,
    )


async def show_dashboard_orders(update: Update):
    blocks = []

    for symbol in ("BTCUSDT", "ETHUSDT"):
        ticker = await asyncio.to_thread(get_ticker, symbol)
        current_price = float(ticker["price"])
        orders = await asyncio.to_thread(
            get_pending_orders,
            current_price,
            100,
            symbol,
        )
        orders = [
            order
            for order in orders
            if str(order.get("status", "")).upper() == "OPEN"
        ]

        if not orders:
            continue

        display_symbol = symbol.replace("USDT", "/USDT")
        price_decimals = 2 if symbol == "ETHUSDT" else 0
        lines = [f"📋 {display_symbol} — {len(orders)}"]

        for order in orders:
            side = str(order.get("side", "")).upper()
            side_icon = "🟢" if side == "BUY" else "🔴"
            quantity = float(order.get("order_quantity") or 0)
            price = float(order.get("order_price") or 0)
            value = float(order.get("order_value") or price * quantity)
            distance = order.get("distance_pct")
            strategy = order.get("strategy_key")
            confidence = order.get("strategy_confidence")

            details = [
                f"{side_icon} {side}",
                f"Цена: {format_number(price, price_decimals)}",
                f"Количество: {quantity:.8f}",
                f"Сумма: {format_number(value, 2)} USDT",
            ]

            if distance is not None:
                details.append(f"До исполнения: {float(distance):.2f}%")

            if strategy:
                strategy_text = str(strategy).title()
                if confidence is not None:
                    strategy_text += f" · {int(confidence)}%"
                details.append(f"Стратегия: {strategy_text}")

            estimated_profit = order.get("estimated_profit_usdt")
            estimated_profit_pct = order.get("estimated_profit_pct")
            if estimated_profit is not None:
                details.append(
                    "Ожидаемый результат: "
                    f"{float(estimated_profit):+.2f} USDT "
                    f"({float(estimated_profit_pct):+.2f}%)"
                )

            order_id = order.get("order_id")
            if order_id:
                details.append(f"Order ID: {order_id}")

            lines.append("\n".join(details))

        blocks.append("\n\n".join(lines))

    if not blocks:
        text = "📋 Открытых ордеров BTC/USDT и ETH/USDT сейчас нет."
    else:
        text = "\n\n────────────\n\n".join(blocks)

    await update.message.reply_text(text, reply_markup=keyboard)


async def show_dashboard_statistics(update: Update):
    blocks = []
    portfolio_profit = 0.0
    portfolio_closed = 0

    for symbol in ("BTCUSDT", "ETHUSDT"):
        ticker = await asyncio.to_thread(get_ticker, symbol)
        current_price = float(ticker["price"])
        data = await asyncio.to_thread(
            get_trades,
            current_price,
            100,
            symbol,
        )
        stats = data["stats"]
        bybit = data["bybit"]
        display_symbol = symbol.replace("USDT", "/USDT")

        portfolio_profit += float(stats["closed_profit_usdt"])
        portfolio_closed += int(stats["closed_count"])

        blocks.append(
            f"""📊 {display_symbol}

Исполнений: {int(bybit["execution_count"])}
Закрытых циклов: {int(stats["closed_count"])}
Открытых позиций: {int(stats["open_count"])}
Стоимость открытых позиций: {float(stats["open_value_usdt"]):.2f} USDT
Результат закрытых сделок: {float(stats["closed_profit_usdt"]):+.2f} USDT
Win Rate: {float(stats["win_rate"]):.1f}%"""
        )

    text = (
        "📈 Статистика Dashboard\n\n"
        + "\n\n────────────\n\n".join(blocks)
        + f"\n\n💼 Общий результат закрытых сделок: "
        f"{portfolio_profit:+.2f} USDT"
        f"\nЗакрытых циклов всего: {portfolio_closed}"
    )
    await update.message.reply_text(text, reply_markup=keyboard)


async def show_dashboard_link(update: Update):
    if not DASHBOARD_URL:
        await update.message.reply_text(
            "Адрес Dashboard ещё не настроен. "
            "Добавь переменную DASHBOARD_URL в Railway.",
            reply_markup=keyboard,
        )
        return

    dashboard_url = DASHBOARD_URL
    if not dashboard_url.startswith(("https://", "http://")):
        dashboard_url = f"https://{dashboard_url}"

    link_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌐 Открыть Dashboard", url=dashboard_url)]]
    )
    await update.message.reply_text(
        "Нажми кнопку ниже, чтобы открыть личный кабинет:",
        reply_markup=link_keyboard,
    )


async def request_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if get_open_trade(user_id):
        await update.message.reply_text(
            "У тебя уже есть открытая сделка. Сначала закрой её.",
            reply_markup=keyboard,
        )
        return

    context.user_data["awaiting_buy_amount"] = True
    await update.message.reply_text(
        "Напиши сумму покупки в USDT.\nНапример: 150\n\n"
        "Цена BTC будет взята автоматически в момент записи."
    )


async def save_buy_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
):
    try:
        amount = float(text.replace(",", ".").strip())
    except ValueError:
        await update.message.reply_text(
            "Напиши только сумму числом. Например: 150"
        )
        return

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть больше нуля.")
        return

    ticker = await asyncio.to_thread(get_ticker)
    price = float(ticker["price"])
    trade_id = open_trade(update.effective_user.id, price, amount)
    context.user_data.pop("awaiting_buy_amount", None)

    await update.message.reply_text(
        f"""🟢 Покупка записана

Сделка: #{trade_id}
Цена: {format_number(price, 2)} USDT
Сумма: {format_number(amount, 2)} USDT

Важно: это цена публичного рынка на момент нажатия, а не точная цена исполнения Bybit.""",
        reply_markup=keyboard,
    )


async def show_open_trade(update: Update):
    trade = get_open_trade(update.effective_user.id)

    if not trade:
        await update.message.reply_text(
            "Открытых сделок нет.",
            reply_markup=keyboard,
        )
        return

    ticker = await asyncio.to_thread(get_ticker)
    current_price = float(ticker["price"])
    entry_price = float(trade["entry_price"])
    change_pct = (current_price - entry_price) / entry_price * 100

    await update.message.reply_text(
        f"""📋 Открытая сделка #{trade["id"]}

Вход: {format_number(entry_price, 2)}
Текущая цена: {format_number(current_price, 2)}
Сумма: {format_number(trade["quote_amount"], 2)} USDT
Изменение до комиссий: {change_pct:+.2f}%""",
        reply_markup=keyboard,
    )


async def sell_trade(update: Update):
    if not get_open_trade(update.effective_user.id):
        await update.message.reply_text(
            "Открытой сделки для продажи нет.",
            reply_markup=keyboard,
        )
        return

    ticker = await asyncio.to_thread(get_ticker)
    result = close_trade(
        update.effective_user.id,
        float(ticker["price"]),
    )

    icon = "✅" if result["net_pnl"] > 0 else "🔻"

    await update.message.reply_text(
        f"""{icon} Сделка #{result["id"]} закрыта

Вход: {format_number(result["entry_price"], 2)}
Выход: {format_number(result["exit_price"], 2)}
Сумма: {format_number(result["quote_amount"], 2)} USDT
Комиссии (примерно): {result["fees"]:.2f} USDT

Чистый результат: {result["net_pnl"]:+.2f} USDT
Доходность: {result["net_pnl_pct"]:+.2f}%""",
        reply_markup=keyboard,
    )


async def show_statistics(update: Update):
    user_id = update.effective_user.id
    manual = get_statistics(user_id)
    bybit = get_bybit_fifo_statistics(user_id)

    if manual["total"] == 0 and bybit["execution_count"] == 0:
        await update.message.reply_text(
            "Статистики пока нет. Запиши сделку вручную или импортируй CSV Bybit.",
            reply_markup=keyboard,
        )
        return

    manual_block = f"""📝 Ручной журнал
Закрыто: {manual["total"]}
Прибыльных: {manual["wins"]}
Убыточных: {manual["losses"]}
Win Rate: {manual["win_rate"]:.1f}%
Чистый результат: {manual["total_net_pnl"]:+.2f} USDT
Средняя доходность: {manual["avg_net_pnl_pct"]:+.2f}%"""

    bybit_block = f"""📥 Импорт Bybit CSV
Исполнений: {bybit["execution_count"]}
Сопоставленных продаж: {bybit["closed_trades"]}
Прибыльных: {bybit["wins"]}
Убыточных: {bybit["losses"]}
Win Rate: {bybit["win_rate"]:.1f}%
Чистый результат: {bybit["total_net_pnl"]:+.2f} USDT
Средняя доходность: {bybit["average_pnl_pct"]:+.2f}%
Остаток: {bybit["open_quantity"]:.8f} BTC
Средняя цена остатка: {bybit["open_average_price"]:.2f} USDT"""

    warning = ""
    if bybit["unmatched_sell_quantity"] > 0:
        warning = (
            "\n\n⚠️ Несопоставлено продаж: "
            f"{bybit['unmatched_sell_quantity']:.8f} BTC. "
            "Для этой части неизвестна первоначальная цена покупки."
        )

    await update.message.reply_text(
        f"""📈 Общая статистика

{manual_block}

{bybit_block}

ℹ️ Источники показаны отдельно, чтобы одна сделка не учитывалась дважды.{warning}""",
        reply_markup=keyboard,
    )


async def request_clear_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_clear_csv_confirmation"] = True
    await update.message.reply_text(
        "Это удалит только импортированные CSV-сделки. "
        "Ручной журнал не изменится.\n\n"
        "Для подтверждения напиши:\nУДАЛИТЬ CSV",
        reply_markup=keyboard,
    )


async def confirm_clear_csv(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
):
    context.user_data.pop("awaiting_clear_csv_confirmation", None)

    if text.strip().upper() != "УДАЛИТЬ CSV":
        await update.message.reply_text(
            "Очистка отменена.",
            reply_markup=keyboard,
        )
        return

    deleted = clear_bybit_executions(update.effective_user.id)
    await update.message.reply_text(
        f"Импортированные данные удалены: {deleted} строк.",
        reply_markup=keyboard,
    )


async def request_csv(update: Update):
    await update.message.reply_text(
        "Пришли CSV-файл истории Spot-сделок из Bybit.eu.\n\n"
        "Бот импортирует только BTC/USDT и пропустит уже загруженные сделки.",
        reply_markup=keyboard,
    )


async def handle_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document

    if not document:
        return

    if document.file_size and document.file_size > 5 * 1024 * 1024:
        await update.message.reply_text(
            "Файл слишком большой. Максимальный размер — 5 МБ.",
            reply_markup=keyboard,
        )
        return

    file_name = (document.file_name or "").lower()
    if not file_name.endswith(".csv"):
        await update.message.reply_text(
            "Нужен файл с расширением .csv.",
            reply_markup=keyboard,
        )
        return

    await update.message.reply_text("Импортирую сделки... ⏳")
    temp_path = None

    try:
        telegram_file = await context.bot.get_file(document.file_id)

        with tempfile.NamedTemporaryFile(
            prefix="bybit_",
            suffix=".csv",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name

        await telegram_file.download_to_drive(custom_path=temp_path)

        report = await asyncio.to_thread(
            import_bybit_csv,
            temp_path,
            update.effective_user.id,
        )
        stats = report["statistics"]

        warning = ""
        if stats["unmatched_sell_quantity"] > 0:
            warning = (
                "\n\n⚠️ Часть продаж не сопоставлена с покупками. "
                "Возможно, CSV начинается позже первоначальной покупки."
            )

        await update.message.reply_text(
            f"""✅ CSV импортирован

Новых исполнений: {report["added"]}
Покупок: {report["buy_rows"]}
Продаж: {report["sell_rows"]}
Дубликатов пропущено: {report["duplicates"]}
Других пар пропущено: {report["ignored"]}

📊 Статистика BTC/USDT из CSV
Закрытых продаж: {stats["closed_trades"]}
Прибыльных: {stats["wins"]}
Убыточных: {stats["losses"]}
Win Rate: {stats["win_rate"]:.1f}%
Чистый результат: {stats["total_net_pnl"]:+.2f} USDT
Средняя доходность: {stats["average_pnl_pct"]:+.2f}%

Остаток BTC по импортированной истории: {stats["open_quantity"]:.8f}
Средняя цена остатка: {stats["open_average_price"]:.2f} USDT{warning}""",
            reply_markup=keyboard,
        )

    except Exception as error:
        await update.message.reply_text(
            f"Ошибка импорта CSV: {error}",
            reply_markup=keyboard,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def make_signal_key(result):
    """Создаёт устойчивый ключ сигнала для защиты от повторных уведомлений."""
    zone = sorted(result["buy_zone_1"])
    symbol = result.get("symbol", "BTCUSDT")
    decimals = 1 if symbol == "ETHUSDT" else 0
    return (
        f'{symbol}:'
        f'{result["grade"]}:'
        f'{zone[0]:.{decimals}f}:'
        f'{zone[1]:.{decimals}f}:'
        f'{int(result["total_score"]) // 5}'
    )


def format_auto_signal(result):
    display_symbol = result.get("display_symbol", "BTC/USDT")
    price_decimals = 2 if display_symbol.startswith("ETH") else 0
    return f"""🔔 АВТОСИГНАЛ {display_symbol}

⭐ Качество: {result["grade"]}
🏆 Оценка: {result["total_score"]}/100
💰 Текущая цена: {format_number(result["price"], price_decimals)}

🤖 Решение стратегии:
{result["decision"]}

🟢 Расчётный вход: до {format_number(result["planned_entry"])}
🎯 Зона покупки 1: {format_zone(result["buy_zone_1"])}
🎯 Зона покупки 2: {format_zone(result["buy_zone_2"])}
🛑 Stop Loss: {format_number(result["stop_loss"])}
💰 Take Profit 1: {format_number(result["take_profit_1"])} (около +1.5%)
🚀 Take Profit 2: {format_number(result["take_profit_2"])} (до +2.0%)
📏 Запас до сопротивления: {result["available_profit_pct"]:.2f}%

Проценты указаны до комиссий. Это информационный сигнал, а не гарантия прибыли."""


async def toggle_auto_signals(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    enabled = toggle_signal_subscription(update.effective_chat.id)

    if enabled:
        text = (
            "🔔 Автоматические сигналы включены.\n\n"
            "Бот проверяет BTC/USDT и ETH/USDT каждые 15 минут и присылает новый сигнал "
            "только при оценке A или A+."
        )
    else:
        text = "🔕 Автоматические сигналы выключены."

    await update.message.reply_text(text, reply_markup=keyboard)


async def check_auto_signals(context: ContextTypes.DEFAULT_TYPE):
    subscribers = get_signal_subscribers()
    if not subscribers:
        return

    symbols = ("BTCUSDT", "ETHUSDT")
    analyses = await asyncio.gather(
        *(
            asyncio.to_thread(analyze_strategy, symbol)
            for symbol in symbols
        ),
        return_exceptions=True,
    )

    for symbol, result in zip(symbols, analyses):
        if isinstance(result, Exception):
            print(
                f"Ошибка автоматической проверки {symbol}: {result}"
            )
            continue

        is_signal = (
            result["grade"] in {"A", "A+"}
            and result["trend_score"] >= 20
            and result["total_score"] >= 75
            and result["target_15_20_available"]
        )
        signal_key = make_signal_key(result) if is_signal else None

        for subscriber in subscribers:
            chat_id = subscriber["telegram_chat_id"]
            previous_keys = {}
            raw_state = subscriber["last_signal_key"]

            if raw_state:
                try:
                    parsed_state = json.loads(raw_state)
                    if isinstance(parsed_state, dict):
                        previous_keys = parsed_state
                except (TypeError, ValueError, json.JSONDecodeError):
                    previous_keys = {}

            previous_key = previous_keys.get(symbol)

            if not is_signal:
                if previous_key is not None:
                    set_last_signal_key(chat_id, None, symbol)
                continue

            if previous_key == signal_key:
                continue

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=format_auto_signal(result),
                    reply_markup=keyboard,
                )
                set_last_signal_key(chat_id, signal_key, symbol)
            except Exception as error:
                print(
                    f"Не удалось отправить сигнал {symbol} "
                    f"в чат {chat_id}: {error}"
                )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    normalized = text.lower()

    try:
        if "анализ btc" in normalized:
            await analyze_asset(update, "BTCUSDT")
        elif "анализ eth" in normalized:
            await analyze_asset(update, "ETHUSDT")
        elif "открытые ордера" in normalized:
            await show_dashboard_orders(update)
        elif "статистика" in normalized:
            await show_dashboard_statistics(update)
        elif "открыть dashboard" in normalized:
            await show_dashboard_link(update)
        elif "автосигналы" in normalized:
            await toggle_auto_signals(update, context)
        else:
            await update.message.reply_text(
                "Выбери действие на клавиатуре.",
                reply_markup=keyboard,
            )
    except Exception as error:
        await update.message.reply_text(
            f"Ошибка: {error}",
            reply_markup=keyboard,
        )


def main():
    if not TELEGRAM_TOKEN:
        print("Ошибка: TELEGRAM_TOKEN не найден в .env")
        return

    init_database()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    app.job_queue.run_repeating(
        check_auto_signals,
        interval=15 * 60,
        first=30,
        name="btc_eth_auto_signals",
    )

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
