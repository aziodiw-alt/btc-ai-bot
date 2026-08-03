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


__all__ = ["grade_fast", "grade_swing"]
