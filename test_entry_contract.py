import unittest

from btc_terminal.strategy.entry import score_fast_entry, score_swing_entry


class EntryScoringContractTest(unittest.TestCase):
    def test_swing_strong_entry_contract(self):
        score, distance, reasons, warnings = score_swing_entry(
            100,
            98,
            103,
            100.5,
        )
        self.assertEqual(score, 20)
        self.assertEqual(distance, 3.0)
        self.assertEqual(
            reasons,
            [
                "До сопротивления есть запас минимум 2%",
                "Цена находится близко к EMA20",
                "Цена относительно близко к поддержке",
            ],
        )
        self.assertEqual(warnings, [])

    def test_swing_boundary_and_warning_contract(self):
        score, distance, reasons, warnings = score_swing_entry(
            100,
            90,
            101.5,
            98,
        )
        self.assertEqual(score, 6)
        self.assertAlmostEqual(distance, 1.5)
        self.assertEqual(reasons, [])
        self.assertEqual(
            warnings,
            [
                "До сопротивления запас только 1.5–2%",
                "Цена далеко от EMA20",
                "Цена далеко от поддержки",
            ],
        )

    def test_fast_strong_entry_contract(self):
        score, distance, reasons, warnings = score_fast_entry(
            100,
            99,
            102,
            100.5,
        )
        self.assertEqual(score, 25)
        self.assertEqual(distance, 2.0)
        self.assertEqual(
            reasons,
            [
                "Fast: до сопротивления есть запас минимум 1,2%",
                "Fast 1H: цена рядом с EMA20",
                "Fast: цена рядом с локальной поддержкой",
            ],
        )
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
