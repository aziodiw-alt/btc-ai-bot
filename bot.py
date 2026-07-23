import asyncio
import os
import tempfile

from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
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


load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

keyboard = ReplyKeyboardMarkup(
    [
        ["📊 Анализ BTC"],
        ["🟢 Записать покупку", "🔴 Записать продажу"],
        ["📋 Открытая сделка", "📈 Статистика"],
        ["📥 Импорт CSV Bybit"],
        ["🗑 Очистить импорт CSV"],
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
    reasons = "\n".join(f"• {item}" for item in result.get("reasons", []))
    warnings = "\n".join(f"• {item}" for item in result.get("warnings", []))

    return f"""📊 BTC/USDT

💰 Цена: {format_number(result["price"])}

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


async def analyze_btc(update):
    await update.message.reply_text(
        "Получаю данные Bybit и считаю индикаторы... ⏳"
    )
    result = await asyncio.to_thread(analyze_strategy)
    await update.message.reply_text(format_analysis(result), reply_markup=keyboard)

    await update.message.reply_text("Готовлю AI-комментарий... 🤖")
    ai_text = await asyncio.to_thread(generate_report, result)
    await update.message.reply_text(
        f"🤖 AI-комментарий:\n\n{ai_text}",
        reply_markup=keyboard,
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
    return (
        f'{result["grade"]}:'
        f'{round(zone[0], -2):.0f}:'
        f'{round(zone[1], -2):.0f}:'
        f'{int(result["total_score"]) // 5}'
    )


def format_auto_signal(result):
    return f"""🔔 АВТОСИГНАЛ BTC/USDT

⭐ Качество: {result["grade"]}
🏆 Оценка: {result["total_score"]}/100
💰 Текущая цена: {format_number(result["price"])}

🤖 Решение стратегии:
{result["decision"]}

🎯 Зона покупки 1: {format_zone(result["buy_zone_1"])}
🎯 Зона покупки 2: {format_zone(result["buy_zone_2"])}
🛑 Stop Loss: {format_number(result["stop_loss"])}
💰 Take Profit 1: {format_number(result["take_profit_1"])}
🚀 Take Profit 2: {format_number(result["take_profit_2"])}

Это информационный сигнал, а не гарантия прибыли. Перед сделкой проверь цену и размер риска."""


async def toggle_auto_signals(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    enabled = toggle_signal_subscription(update.effective_chat.id)

    if enabled:
        text = (
            "🔔 Автоматические сигналы включены.\n\n"
            "Бот проверяет рынок каждые 15 минут и присылает новый сигнал "
            "только при оценке A или A+."
        )
    else:
        text = "🔕 Автоматические сигналы выключены."

    await update.message.reply_text(text, reply_markup=keyboard)


async def check_auto_signals(context: ContextTypes.DEFAULT_TYPE):
    subscribers = get_signal_subscribers()
    if not subscribers:
        return

    try:
        result = await asyncio.to_thread(analyze_strategy)
    except Exception as error:
        print(f"Ошибка автоматической проверки рынка: {error}")
        return

    is_signal = (
        result["grade"] in {"A", "A+"}
        and result["trend_score"] >= 20
        and result["total_score"] >= 75
    )

    signal_key = make_signal_key(result) if is_signal else None

    for subscriber in subscribers:
        chat_id = subscriber["telegram_chat_id"]
        previous_key = subscriber["last_signal_key"]

        if not is_signal:
            if previous_key is not None:
                set_last_signal_key(chat_id, None)
            continue

        if previous_key == signal_key:
            continue

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=format_auto_signal(result),
                reply_markup=keyboard,
            )
            set_last_signal_key(chat_id, signal_key)
        except Exception as error:
            print(f"Не удалось отправить сигнал в чат {chat_id}: {error}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    normalized = text.lower()

    try:
        if context.user_data.get("awaiting_clear_csv_confirmation"):
            await confirm_clear_csv(update, context, text)
        elif context.user_data.get("awaiting_buy_amount"):
            await save_buy_amount(update, context, text)
        elif "анализ btc" in normalized:
            await analyze_btc(update)
        elif "записать покупку" in normalized:
            await request_buy(update, context)
        elif "записать продажу" in normalized:
            await sell_trade(update)
        elif "открытая сделка" in normalized:
            await show_open_trade(update)
        elif "статистика" in normalized:
            await show_statistics(update)
        elif "автосигналы" in normalized:
            await toggle_auto_signals(update, context)
        elif "очистить импорт csv" in normalized:
            await request_clear_csv(update, context)
        elif "импорт csv" in normalized:
            await request_csv(update)
        else:
            await update.message.reply_text(
                "Выбери действие кнопкой ниже.",
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
        MessageHandler(filters.Document.FileExtension("csv"), handle_csv)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    app.job_queue.run_repeating(
        check_auto_signals,
        interval=15 * 60,
        first=30,
        name="btc_auto_signals",
    )

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
