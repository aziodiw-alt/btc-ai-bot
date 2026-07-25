import re
import threading
import time
from html import unescape
from html.parser import HTMLParser
from urllib.request import Request, urlopen


CHANNEL_URL = "https://t.me/s/whale_alert_io"
CACHE_SECONDS = 300
REQUEST_TIMEOUT = 6
TRACKED_SYMBOLS = {"BTC", "USDT", "USDC"}
EXCHANGES = {
    "binance", "bitfinex", "bitstamp", "bybit", "coinbase",
    "coinbase institutional", "crypto.com", "gemini", "kraken",
    "kucoin", "okx",
}

_cache_lock = threading.Lock()
_cache = {"timestamp": 0.0, "payload": None}


class _TelegramChannelParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current_post = None
        self.collecting = False
        self.depth = 0
        self.parts = []
        self.messages = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if attributes.get("data-post"):
            self.current_post = attributes["data-post"]

        classes = set(attributes.get("class", "").split())

        if "tgme_widget_message_text" in classes:
            self.collecting = True
            self.depth = 1
            self.parts = []
        elif self.collecting:
            self.depth += 1

    def handle_data(self, data):
        if self.collecting:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if not self.collecting:
            return

        self.depth -= 1

        if self.depth > 0:
            return

        text = " ".join(" ".join(self.parts).split())

        if text:
            self.messages.append({
                "text": unescape(text),
                "url": (
                    f"https://t.me/{self.current_post}"
                    if self.current_post
                    else CHANNEL_URL
                ),
            })

        self.collecting = False
        self.parts = []


def _is_exchange(name):
    normalized = (
        str(name).replace("#", "").replace("withdrawals", "")
        .strip().lower()
    )
    return any(
        exchange == normalized or exchange in normalized
        for exchange in EXCHANGES
    )


def _parse_message(message):
    text = message["text"]
    symbol_match = re.search(r"\$(BTC|USDT|USDC)\b", text, re.IGNORECASE)
    usd_match = re.search(
        r"\(([\d,]+(?:\.\d+)?)\s+USD\)",
        text,
        re.IGNORECASE,
    )

    if not symbol_match or not usd_match:
        return None

    symbol = symbol_match.group(1).upper()
    value_usd = float(usd_match.group(1).replace(",", ""))
    lower_text = text.lower()
    event_type = "transfer"
    from_name = ""
    to_name = ""

    if " minted " in f" {lower_text} ":
        event_type = "mint"
    elif " burned " in f" {lower_text} ":
        event_type = "burn"
    else:
        direction_match = re.search(
            r"transferred from (.+?) to (.+?)(?:\s+details|$)",
            text,
            re.IGNORECASE,
        )
        if direction_match:
            from_name = direction_match.group(1).strip()
            to_name = direction_match.group(2).strip()

    from_exchange = _is_exchange(from_name)
    to_exchange = _is_exchange(to_name)
    impact = 0
    category = "Нейтральный перевод"

    if symbol == "BTC":
        if to_exchange and not from_exchange:
            impact, category = -2, "BTC поступает на биржу"
        elif from_exchange and not to_exchange:
            impact, category = 2, "BTC выводится с биржи"
    elif event_type == "mint":
        impact, category = 1, f"Выпуск {symbol}"
    elif event_type == "burn":
        impact, category = -1, f"Сжигание {symbol}"
    elif to_exchange and not from_exchange:
        impact, category = 1, f"{symbol} поступает на биржу"
    elif from_exchange and not to_exchange:
        impact, category = -1, f"{symbol} выводится с биржи"

    return {
        "symbol": symbol,
        "value_usd": value_usd,
        "value_millions": round(value_usd / 1_000_000, 1),
        "category": category,
        "impact": impact,
        "url": message["url"],
    }


def _empty_payload(error=None):
    return {
        "available": False,
        "activity": "Нет данных",
        "sentiment": "Нейтрально",
        "score": 0,
        "events": [],
        "totals": {
            "btc_to_exchanges": 0.0,
            "btc_from_exchanges": 0.0,
            "stable_to_exchanges": 0.0,
        },
        "error": error,
        "source_url": CHANNEL_URL,
    }


def _download_and_analyze():
    request = Request(
        CHANNEL_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            )
        },
    )

    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = _TelegramChannelParser()
    parser.feed(html)
    events = []

    for message in parser.messages:
        event = _parse_message(message)
        if not event:
            continue

        threshold = 20_000_000 if event["symbol"] == "BTC" else 100_000_000
        if event["value_usd"] >= threshold:
            events.append(event)

    events = events[-8:][::-1]
    score = sum(event["impact"] for event in events)
    total_value = sum(event["value_usd"] for event in events)

    def total_for(category):
        return round(sum(
            event["value_usd"] for event in events
            if event["category"] == category
        ) / 1_000_000, 1)

    stable_to_exchanges = round(sum(
        event["value_usd"] for event in events
        if event["category"] in {
            "USDT поступает на биржу",
            "USDC поступает на биржу",
        }
    ) / 1_000_000, 1)

    sentiment = (
        "Умеренно позитивно" if score >= 3
        else "Умеренно негативно" if score <= -3
        else "Нейтрально"
    )
    activity = (
        "Высокая" if total_value >= 1_000_000_000 or len(events) >= 6
        else "Повышенная" if events
        else "Спокойная"
    )

    return {
        "available": True,
        "activity": activity,
        "sentiment": sentiment,
        "score": score,
        "events": events,
        "totals": {
            "btc_to_exchanges": total_for("BTC поступает на биржу"),
            "btc_from_exchanges": total_for("BTC выводится с биржи"),
            "stable_to_exchanges": stable_to_exchanges,
        },
        "error": None,
        "source_url": CHANNEL_URL,
    }


def get_whale_context(force=False):
    now = time.time()

    with _cache_lock:
        cached = _cache["payload"]
        if (
            not force and cached is not None
            and now - _cache["timestamp"] < CACHE_SECONDS
        ):
            return cached

        try:
            payload = _download_and_analyze()
        except Exception as exc:
            payload = _empty_payload(str(exc))
            if cached is not None:
                payload = {
                    **cached,
                    "error": "Не удалось обновить канал; показаны последние данные.",
                }

        _cache["timestamp"] = now
        _cache["payload"] = payload
        return payload
