"""Run the deterministic test suite without exchange or OpenAI calls."""

import sys
import unittest


OFFLINE_TEST_MODULES = (
    "test_strategy",
    "test_fast_strategy",
    "test_bot_formatting",
    "test_web_analysis_contract",
    "test_storage_contract",
    "test_levels",
    "test_market_state",
    "test_okx_client",
    "test_pending_order_profit",
    "test_sell_advice",
    "test_package_boundaries",
    "test_indicator_contract",
    "test_market_provider_contract",
    "test_market_adapters",
    "test_sentiment",
    "test_grading_contract",
    "test_risk_contract",
    "test_trend_contract",
    "test_entry_contract",
    "test_momentum_contract",
    "test_selection_contract",
    "test_analysis_service_contract",
    "test_trade_calculations",
    "test_coinglass_module",
    "test_deployment_contract",
)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        OFFLINE_TEST_MODULES
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
