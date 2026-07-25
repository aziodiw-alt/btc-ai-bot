import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen


SOURCE_URL = "https://cryptonews.com/news/bitcoin-news/"
FEED_URLS = (
    "https://cryptonews.com/news/bitcoin-news/feed/",
    "https://cryptonews.com/news/feed/",
    "https://cryptonews.com/feed/",
)
CACHE_SECONDS = 600
REQUEST_TIMEOUT = 7
MAX_ARTICLES = 8

POSITIVE_WORDS = {
    "adoption", "approval", "approved", "bullish", "breakout", "gain",
    "gains", "inflow", "inflows", "rally", "rebound", "record", "rise",
    "rises", "surge", "surges", "buys", "accumulation",
}
NEGATIVE_WORDS = {
    "ban", "bearish", "crash", "drop", "falls", "fall", "hack",
    "hacked", "lawsuit", "liquidation", "outflow", "outflows", "probe",
    "risk", "sell-off", "stolen", "warning", "fraud", "exploit",
}
HIGH_IMPORTANCE_WORDS = {
    "bitcoin", "btc", "etf", "sec", "fed", "federal reserve", "rate",
    "regulation", "government", "institutional", "treasury", "hack",
    "exploit", "liquidation", "binance", "coinbase", "bybit",
}

_cache_lock = threading.Lock()
_cache = {"timestamp": 0.0, "payload": None}


class _HeadlineParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current_href = None
        self.depth = 0
        self.parts = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        if self.current_href is not None:
            self.depth += 1
            return

        if tag != "a":
            return

        href = dict(attrs).get("href", "")
        if "/news/" not in href:
            return

        self.current_href = urljoin(SOURCE_URL, href)
        self.depth = 1
        self.parts = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.current_href is None:
            return

        self.depth -= 1
        if self.depth > 0:
            return

        title = " ".join(" ".join(self.parts).split())
        if len(title) >= 25:
            self.items.append({
                "title": unescape(title),
                "url": self.current_href,
                "published": "",
            })

        self.current_href = None
        self.parts = []


def _download(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
            "Accept": (
                "application/rss+xml, application/xml, text/xml, "
                "text/html;q=0.9, */*;q=0.8"
            ),
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def _parse_feed(content):
    root = ET.fromstring(content)
    articles = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()

        if not title or not link:
            continue

        try:
            published = parsedate_to_datetime(published).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass

        articles.append({
            "title": unescape(title),
            "url": link,
            "published": published,
        })

    return articles


def _parse_html(content):
    text = content.decode("utf-8", errors="replace")
    parser = _HeadlineParser()
    parser.feed(text)

    # Some page versions expose article data only through JSON-LD.
    for raw_json in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(unescape(raw_json))
        except (json.JSONDecodeError, TypeError):
            continue

        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = node.get("headline") or node.get("name")
            url = node.get("url")
            if title and url:
                parser.items.append({
                    "title": str(title),
                    "url": str(url),
                    "published": str(node.get("datePublished") or ""),
                })

    return parser.items


def _headline_score(title):
    words = set(re.findall(r"[a-z][a-z-]+", title.lower()))
    score = len(words & POSITIVE_WORDS) - len(words & NEGATIVE_WORDS)
    return max(-2, min(2, score))


def _importance(title):
    lower = title.lower()
    matches = sum(word in lower for word in HIGH_IMPORTANCE_WORDS)
    if matches >= 2:
        return "Высокая"
    if matches == 1:
        return "Средняя"
    return "Низкая"


def _is_relevant(title):
    lower = title.lower()
    return any(term in lower for term in (
        "bitcoin", " btc ", "crypto", "fed", "sec", "etf",
        "regulation", "binance", "coinbase", "bybit",
    ))


def _analyze_articles(articles):
    seen = set()
    analyzed = []

    for article in articles:
        title = " ".join(str(article["title"]).split())
        key = title.casefold()

        if key in seen or not _is_relevant(f" {title} "):
            continue

        seen.add(key)
        score = _headline_score(title)
        analyzed.append({
            **article,
            "title": title,
            "score": score,
            "sentiment": (
                "Позитивно" if score > 0
                else "Негативно" if score < 0
                else "Нейтрально"
            ),
            "importance": _importance(title),
        })

        if len(analyzed) >= MAX_ARTICLES:
            break

    total_score = sum(
        item["score"] * (2 if item["importance"] == "Высокая" else 1)
        for item in analyzed
    )
    sentiment = (
        "Умеренно позитивно" if total_score >= 3
        else "Умеренно негативно" if total_score <= -3
        else "Нейтрально"
    )
    high_importance_count = sum(
        item["importance"] == "Высокая" for item in analyzed
    )

    return {
        "available": True,
        "sentiment": sentiment,
        "score": total_score,
        "high_importance_count": high_importance_count,
        "articles": analyzed,
        "source_url": SOURCE_URL,
        "error": None,
    }


def _download_and_analyze():
    last_error = None

    for feed_url in FEED_URLS:
        try:
            articles = _parse_feed(_download(feed_url))
            if articles:
                return _analyze_articles(articles)
        except Exception as exc:
            last_error = exc

    try:
        articles = _parse_html(_download(SOURCE_URL))
        if articles:
            return _analyze_articles(articles)
    except Exception as exc:
        last_error = exc

    raise ValueError(
        f"CryptoNews не вернул новости: {last_error or 'пустой ответ'}"
    )


def get_news_context(force=False):
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
            payload = {
                "available": False,
                "sentiment": "Нейтрально",
                "score": 0,
                "high_importance_count": 0,
                "articles": [],
                "source_url": SOURCE_URL,
                "error": str(exc),
            }
            if cached is not None:
                payload = {
                    **cached,
                    "error": "Не удалось обновить новости; показаны последние данные.",
                }

        _cache["timestamp"] = now
        _cache["payload"] = payload
        return payload
