import unittest

from coinglass import get_sentiment


class LegacyCoinglassContractTest(unittest.TestCase):
    def test_fixture_sentiment_shape_and_score_are_stable(self):
        result = get_sentiment()

        self.assertEqual(result["funding"], 0.008)
        self.assertEqual(result["long_short"], 1.15)
        self.assertEqual(result["open_interest_change"], 2.3)
        self.assertEqual(result["sentiment_score"], 30)
        self.assertEqual(len(result["reasons"]), 3)


if __name__ == "__main__":
    unittest.main()
