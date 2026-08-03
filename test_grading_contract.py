import unittest

from btc_terminal.strategy.grading import grade_fast, grade_swing


class GradingContractTest(unittest.TestCase):
    def test_swing_boundaries_and_decisions(self):
        cases = (
            (85, "A+", "BUY LIMIT — хороший сигнал"),
            (75, "A", "WAIT / BUY LIMIT на откате"),
            (65, "B", "WAIT — условия средние"),
            (50, "C", "SKIP — слабый вход"),
            (49, "SKIP", "SKIP — вход не рекомендуется"),
        )
        for score, grade, decision in cases:
            with self.subTest(score=score):
                self.assertEqual(
                    grade_swing(score, "UPTREND"),
                    (grade, decision),
                )

    def test_fast_boundaries_and_decisions(self):
        cases = (
            (85, "A+", "FAST BUY LIMIT — сильный короткий сигнал"),
            (75, "A", "FAST BUY LIMIT — допустим небольшой объём"),
            (65, "B", "FAST WAIT — ждать более точного входа"),
            (64, "SKIP", "FAST SKIP — преимущества недостаточно"),
        )
        for score, grade, decision in cases:
            with self.subTest(score=score):
                self.assertEqual(
                    grade_fast(score, "RANGE"),
                    (grade, decision),
                )

    def test_downtrend_overrides_score_for_both_profiles(self):
        self.assertEqual(
            grade_swing(100, "DOWNTREND"),
            ("SKIP", "SKIP — нисходящий тренд"),
        )
        self.assertEqual(
            grade_fast(100, "DOWNTREND"),
            ("SKIP", "FAST SKIP — нисходящий режим рынка"),
        )


if __name__ == "__main__":
    unittest.main()
