import unittest

from app.analytics import demand_forecast, linear_trend, shortage_risk


class AnalyticsTests(unittest.TestCase):
    def test_linear_trend(self):
        self.assertEqual(linear_trend([2, 4, 6]), (2.0, 2.0))

    def test_forecast_returns_requested_horizon(self):
        result = demand_forecast([("2025-01", 10), ("2025-02", 20), ("2026-01", 15)], 2)
        self.assertEqual(len(result), 2)
        self.assertGreaterEqual(result[0]["quantity"], 0)

    def test_risk_increases_for_low_stock(self):
        risk = shortage_risk([100, 120, 90], stock=5, lead_time_days=30)
        self.assertGreaterEqual(risk["score"], 60)

    def test_seasonal_acceleration_is_reflected_in_risk(self):
        baseline = shortage_risk([100, 100, 100], stock=100, lead_time_days=10, next_forecast=100)
        growing = shortage_risk([100, 100, 100], stock=100, lead_time_days=10, next_forecast=200)
        self.assertGreater(growing["score"], baseline["score"])
        self.assertGreater(growing["seasonality_component"], 0)


if __name__ == "__main__":
    unittest.main()
