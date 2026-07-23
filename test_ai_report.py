"""
Отдельная проверка модуля ai_report.py.

Запуск из папки проекта:
    python test_ai_report.py
"""

from dotenv import load_dotenv

# Загружаем OPENAI_API_KEY из файла .env до импорта AI-модуля.
load_dotenv()

from ai_report import generate_report


TEST_RESULT = {
    "price": 65128.70,
    "trend_score": 15,
    "entry_score": 15,
    "indicators_score": 5,
    "sentiment_score": 30,
    "total_score": 65,
    "score_max": 100,
    "grade": "SKIP",
    "decision": "SKIP — слабый дневной тренд",
    "reasons": [
        "4H: цена выше EMA200",
        "Цена находится близко к EMA20",
        "Funding нейтральный",
        "Open Interest умеренно растет",
    ],
    "warnings": [
        "1D: цена ниже EMA200",
        "1D: EMA20 ниже EMA50",
        "Главный фильтр: тренд слишком слабый",
    ],
}


def main():
    print("Проверяю ai_report.py...")
    print("Запрос к OpenAI может занять несколько секунд.\n")

    try:
        report = generate_report(TEST_RESULT)
    except Exception as error:
        print("Ошибка проверки AI-модуля:")
        print(error)
        print(
            "\nПроверьте OPENAI_API_KEY в .env, баланс OpenAI API "
            "и название модели в ai_report.py."
        )
        return

    print("AI-модуль работает ✅\n")
    print("Ответ AI:")
    print(report)


if __name__ == "__main__":
    main()
