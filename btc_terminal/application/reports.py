"""AI report orchestration independent from Flask transport."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from btc_terminal.core.constants import AI_REPORT_CACHE_TTL_SECONDS


class AIReportService:
    def __init__(
        self,
        strategy_loader,
        whale_loader,
        news_loader,
        report_generator_loader,
        *,
        cache_ttl=AI_REPORT_CACHE_TTL_SECONDS,
        clock=time.monotonic,
    ):
        self.strategy_loader = strategy_loader
        self.whale_loader = whale_loader
        self.news_loader = news_loader
        self.report_generator_loader = report_generator_loader
        self.cache_ttl = cache_ttl
        self.clock = clock
        self.cache = {
            "signature": None,
            "created_at": 0.0,
            "value": None,
        }
        self.lock = threading.Lock()

    def generate(self, strategy_name, symbol):
        result = self.strategy_loader(strategy_name, symbol)
        with ThreadPoolExecutor(max_workers=2) as executor:
            whale_future = executor.submit(self.whale_loader)
            news_future = executor.submit(self.news_loader)
            whale_context = whale_future.result()
            news_context = news_future.result()

        signature = self._signature(
            strategy_name,
            symbol,
            result,
            whale_context,
            news_context,
        )
        now = self.clock()
        with self.lock:
            if (
                self.cache["value"] is not None
                and self.cache["signature"] == signature
                and now - self.cache["created_at"] < self.cache_ttl
            ):
                return {"report": self.cache["value"], "cached": True}

        report = self.report_generator_loader()(
            result,
            whale_context=whale_context,
            news_context=news_context,
        )
        with self.lock:
            self.cache.update({
                "signature": signature,
                "created_at": self.clock(),
                "value": report,
            })
        return {"report": report, "cached": False}

    @staticmethod
    def _signature(
        strategy_name, symbol, result, whale_context, news_context
    ):
        return (
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


__all__ = ["AIReportService"]
