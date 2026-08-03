"""Pure post-grading safety filters for current strategy profiles."""


def apply_swing_safety_filters(
    grade,
    decision,
    *,
    market_state_key,
    entry_score,
    target_available,
):
    if (
        market_state_key == "RANGE"
        and grade in {"A", "A+"}
        and entry_score < 15
    ):
        return (
            "B",
            "WAIT — в диапазоне ждём цену возле поддержки",
            "Range-фильтр: текущая цена ещё не находится в качественной зоне входа",
        )
    if grade in {"A", "A+"} and not target_available:
        return (
            "B",
            "WAIT — до безопасной цели нет запаса 1.5%",
            "Автосигнал заблокирован: потенциал до сопротивления меньше 1.5%",
        )
    if grade in {"A", "A+"}:
        return (
            grade,
            "BUY LIMIT — доступна цель примерно 1.5–2%",
            None,
        )
    return grade, decision, None


def apply_fast_safety_filters(
    grade,
    decision,
    *,
    available_profit_pct,
):
    if grade in {"A", "A+"} and available_profit_pct < 0.8:
        return (
            "B",
            "FAST WAIT — до цели нет запаса 0,8%",
            "Fast-сигнал заблокирован близким сопротивлением",
        )
    return grade, decision, None


__all__ = ["apply_fast_safety_filters", "apply_swing_safety_filters"]
