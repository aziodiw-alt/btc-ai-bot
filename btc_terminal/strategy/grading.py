"""Pure base grading rules for current strategy profiles."""

from btc_terminal.core.constants import (
    GRADE_A_PLUS_MIN_SCORE,
    GRADE_A_MIN_SCORE,
    GRADE_B_MIN_SCORE,
    GRADE_C_MIN_SCORE,
)


def grade_swing(total_score, market_state_key):
    if market_state_key == "DOWNTREND":
        return "SKIP", "SKIP — нисходящий тренд"
    if total_score >= GRADE_A_PLUS_MIN_SCORE:
        return "A+", "BUY LIMIT — хороший сигнал"
    if total_score >= GRADE_A_MIN_SCORE:
        return "A", "WAIT / BUY LIMIT на откате"
    if total_score >= GRADE_B_MIN_SCORE:
        return "B", "WAIT — условия средние"
    if total_score >= GRADE_C_MIN_SCORE:
        return "C", "SKIP — слабый вход"
    return "SKIP", "SKIP — вход не рекомендуется"


def grade_fast(total_score, market_state_key):
    if market_state_key == "DOWNTREND":
        return "SKIP", "FAST SKIP — нисходящий режим рынка"
    if total_score >= GRADE_A_PLUS_MIN_SCORE:
        return "A+", "FAST BUY LIMIT — сильный короткий сигнал"
    if total_score >= GRADE_A_MIN_SCORE:
        return "A", "FAST BUY LIMIT — допустим небольшой объём"
    if total_score >= GRADE_B_MIN_SCORE:
        return "B", "FAST WAIT — ждать более точного входа"
    return "SKIP", "FAST SKIP — преимущества недостаточно"


def grade_alpha(
    total_score,
    *,
    trend_score,
    sharp_upward_momentum,
    target_available,
):
    if sharp_upward_momentum or trend_score < 25 or not target_available:
        return "SKIP", "ALPHA WAIT - вход только после спокойного отката"
    if total_score >= GRADE_A_PLUS_MIN_SCORE:
        return "A+", "ALPHA BUY LIMIT - использовать входы 20% / 30% / 50%"
    if total_score >= GRADE_A_MIN_SCORE:
        return "A", "ALPHA WAIT / BUY LIMIT - дождаться первой зоны"
    if total_score >= GRADE_B_MIN_SCORE:
        return "B", "ALPHA WAIT - условия пока средние"
    return "SKIP", "ALPHA SKIP - консервативного преимущества нет"


__all__ = ["grade_alpha", "grade_fast", "grade_swing"]
