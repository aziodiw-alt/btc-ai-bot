import os

from dotenv import load_dotenv
from openai import OpenAI


# Загружаем секретный ключ из файла .env.
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError(
        "OPENAI_API_KEY не найден. Откройте файл .env и добавьте строку:\n"
        "OPENAI_API_KEY=ваш_новый_ключ"
    )

client = OpenAI(api_key=api_key)


def generate_report(result):
    reasons = "\n".join(result.get("reasons", [])) or "Нет"
    warnings = "\n".join(result.get("warnings", [])) or "Нет"

    prompt = f"""
Ты объясняешь результат автоматической стратегии анализа BTC/USDT.
Не изменяй торговое решение стратегии и не обещай прибыль.

Цена: {result["price"]}
Trend: {result["trend_score"]}/40
Entry: {result["entry_score"]}/20
Indicators: {result["indicators_score"]}/10
Sentiment: {result["sentiment_score"]}/30
Итог: {result["total_score"]}/100
Grade: {result["grade"]}
Решение: {result["decision"]}

Положительные факторы:
{reasons}

Предупреждения:
{warnings}

Кратко и простым русским языком объясни:
1. Почему стратегия приняла такое решение.
2. Какие факторы положительные.
3. Какие риски важнее всего.
4. Что должно измениться для улучшения сигнала.

Не более 150 слов.
""".strip()

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
    )

    return response.output_text
