def get_sentiment():
    """
    Пока тестовые данные.
    Позже заменим на API CoinGlass.
    """

    data = {
        "funding": 0.008,
        "long_short": 1.15,
        "open_interest_change": 2.3
    }

    score = 0
    reasons = []

    # Funding
    if abs(data["funding"]) < 0.01:
        score += 10
        reasons.append("Funding нейтральный")
    else:
        reasons.append("Funding перегрет")

    # Long / Short
    if 0.8 <= data["long_short"] <= 1.4:
        score += 10
        reasons.append("Long/Short сбалансирован")
    else:
        reasons.append("Long/Short перекошен")

    # Open Interest
    if data["open_interest_change"] > 0:
        score += 10
        reasons.append("Open Interest растет")
    else:
        reasons.append("Open Interest падает")

    data["sentiment_score"] = score
    data["reasons"] = reasons

    return data