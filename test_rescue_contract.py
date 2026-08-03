import unittest

from btc_terminal.application.rescue import calculate_rescue_plan


class AlphaRescueContractTest(unittest.TestCase):
    def test_btc_cycle_targets_one_percent_more_btc_after_two_fees(self):
        result = calculate_rescue_plan(
            "BTC",
            0.01,
            0.03,
            fee_rate=0.001,
            minimum_net_gain_pct=1.0,
            base_usd_price=60_000,
            average_cost_usd=62_000,
        )

        self.assertEqual(result["action"], "BTC → ETH → BTC")
        self.assertEqual(result["required_cross_direction"], "UP")
        self.assertAlmostEqual(result["base_quantity_after"], 0.0101)
        self.assertAlmostEqual(result["net_gain_pct"], 1.0)
        self.assertTrue(result["target_met"])
        self.assertTrue(result["usd_risk_remains"])
        self.assertLess(result["projected_recovery_gap_usd"], 0)

    def test_eth_cycle_targets_one_percent_more_eth_on_cross_decline(self):
        result = calculate_rescue_plan(
            "ETH",
            2.0,
            0.03,
            fee_rate=0.001,
            minimum_net_gain_pct=1.0,
        )

        self.assertEqual(result["action"], "ETH → BTC → ETH")
        self.assertEqual(result["required_cross_direction"], "DOWN")
        self.assertLess(result["cross_exit_price"], 0.03)
        self.assertAlmostEqual(result["base_quantity_after"], 2.02)
        self.assertAlmostEqual(result["net_gain_pct"], 1.0)

    def test_invalid_or_unsupported_position_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "only BTC or ETH"):
            calculate_rescue_plan("SOL", 1, 0.03)
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            calculate_rescue_plan("BTC", 0, 0.03)


if __name__ == "__main__":
    unittest.main()
