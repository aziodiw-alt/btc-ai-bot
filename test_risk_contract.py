import unittest

from btc_terminal.strategy.risk import (
    apply_fast_safety_filters,
    apply_swing_safety_filters,
)


class RiskFilterContractTest(unittest.TestCase):
    def test_swing_range_filter_has_priority_over_target_filter(self):
        self.assertEqual(
            apply_swing_safety_filters(
                "A+",
                "BASE",
                market_state_key="RANGE",
                entry_score=14,
                target_available=False,
            ),
            (
                "B",
                "WAIT — в диапазоне ждём цену возле поддержки",
                "Range-фильтр: текущая цена ещё не находится в качественной зоне входа",
            ),
        )

    def test_swing_target_filter_and_success_decision(self):
        self.assertEqual(
            apply_swing_safety_filters(
                "A",
                "BASE",
                market_state_key="UPTREND",
                entry_score=20,
                target_available=False,
            ),
            (
                "B",
                "WAIT — до безопасной цели нет запаса 1.5%",
                "Автосигнал заблокирован: потенциал до сопротивления меньше 1.5%",
            ),
        )
        self.assertEqual(
            apply_swing_safety_filters(
                "A",
                "BASE",
                market_state_key="UPTREND",
                entry_score=20,
                target_available=True,
            ),
            ("A", "BUY LIMIT — доступна цель примерно 1.5–2%", None),
        )

    def test_non_buy_swing_grade_is_unchanged(self):
        self.assertEqual(
            apply_swing_safety_filters(
                "B",
                "BASE",
                market_state_key="RANGE",
                entry_score=0,
                target_available=False,
            ),
            ("B", "BASE", None),
        )

    def test_fast_target_filter_boundary(self):
        self.assertEqual(
            apply_fast_safety_filters(
                "A+",
                "BASE",
                available_profit_pct=0.79,
            ),
            (
                "B",
                "FAST WAIT — до цели нет запаса 0,8%",
                "Fast-сигнал заблокирован близким сопротивлением",
            ),
        )
        self.assertEqual(
            apply_fast_safety_filters(
                "A+",
                "BASE",
                available_profit_pct=0.8,
            ),
            ("A+", "BASE", None),
        )


if __name__ == "__main__":
    unittest.main()
