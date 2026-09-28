import unittest

from app.analytics import (
    CPRI_WEIGHTS,
    calibrate_cpri_weights,
    demand_forecast,
    forecast_accuracy,
    linear_trend,
    procurement_recommendation,
    seasonal_naive_forecast,
    shortage_risk,
    validate_weights,
)


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

    def test_backtesting_returns_standard_error_metrics(self):
        monthly = [(f"2025-{month:02d}", float(month * 10)) for month in range(1, 11)]
        result = forecast_accuracy(monthly, min_train_periods=4)
        self.assertEqual(result["observations"], 6)
        self.assertIsNotNone(result["mae"])
        self.assertIsNotNone(result["rmse"])
        self.assertIsNotNone(result["mape"])

    def test_seasonal_naive_uses_same_month_of_previous_year(self):
        monthly = [("2025-03", 40.0), ("2025-04", 55.0), ("2026-01", 10.0)]
        self.assertEqual(seasonal_naive_forecast(monthly, "2026-04"), 55.0)
        self.assertIsNone(seasonal_naive_forecast(monthly, "2026-05"))

    def test_backtesting_compares_model_with_seasonal_naive_baseline(self):
        pattern = [
            10.0,
            12.0,
            14.0,
            16.0,
            18.0,
            20.0,
            19.0,
            17.0,
            15.0,
            13.0,
            11.0,
            9.0,
        ]
        monthly = [(f"2025-{m:02d}", v) for m, v in enumerate(pattern, start=1)]
        monthly += [(f"2026-{m:02d}", v * 2) for m, v in enumerate(pattern, start=1)]
        result = forecast_accuracy(monthly, min_train_periods=6)
        baseline = result["baseline"]
        # Baseline is only scored where the same month of the previous year exists.
        self.assertEqual(baseline["observations"], 12)
        # Naive forecast for 2026 equals 2025, so its error is exactly the 2025 value.
        self.assertAlmostEqual(baseline["mae"], sum(pattern) / 12, places=2)
        expected_gain = round((baseline["mae"] - baseline["model_mae"]) / baseline["mae"] * 100, 2)
        self.assertEqual(baseline["gain_pct"], expected_gain)

    def test_baseline_is_empty_without_a_full_year_of_history(self):
        monthly = [(f"2025-{month:02d}", float(month * 10)) for month in range(1, 11)]
        baseline = forecast_accuracy(monthly, min_train_periods=4)["baseline"]
        self.assertEqual(baseline["observations"], 0)
        self.assertIsNone(baseline["mae"])
        self.assertIsNone(baseline["gain_pct"])

    def test_default_weights_keep_expert_cpri_unchanged(self):
        self.assertEqual(sum(CPRI_WEIGHTS.values()), 1.0)
        risk = shortage_risk([100, 120, 90], stock=50, lead_time_days=20, next_forecast=130)
        self.assertEqual(
            risk,
            shortage_risk(
                [100, 120, 90],
                stock=50,
                lead_time_days=20,
                next_forecast=130,
                weights=CPRI_WEIGHTS,
            ),
        )
        self.assertEqual(risk["score"], 60.2)

    def test_custom_weights_change_score(self):
        only_lead = {"demand": 0.0, "volatility": 0.0, "lead": 1.0, "seasonality": 0.0}
        risk = shortage_risk([100, 100, 100], stock=1000, lead_time_days=15, weights=only_lead)
        self.assertEqual(risk["score"], 50.0)

    def test_invalid_weights_are_rejected(self):
        for weights in (
            {"demand": 0.5, "volatility": 0.5, "lead": 0.5, "seasonality": 0.5},
            {"demand": 1.2, "volatility": -0.2, "lead": 0.0, "seasonality": 0.0},
            {"demand": 1.0},
        ):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                validate_weights(weights)

    def test_cpri_calibration_returns_valid_non_worse_recommendation(self):
        scenarios = [
            {
                "values": [20.0, 22.0, 24.0, 26.0, 28.0, 30.0],
                "stock": 30.0,
                "lead_time_days": 30,
                "forecast": 30.0,
                "actual": 40.0,
            },
            {
                "values": [10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
                "stock": 100.0,
                "lead_time_days": 10,
                "forecast": 20.0,
                "actual": 10.0,
            },
        ]
        result = calibrate_cpri_weights(scenarios)
        self.assertEqual(result["observations"], 2)
        self.assertEqual(sum(result["weights"].values()), 1.0)
        self.assertLessEqual(result["mae"], result["expert_mae"])

    def test_cpri_calibration_handles_missing_history(self):
        result = calibrate_cpri_weights([])
        self.assertIsNone(result["weights"])
        self.assertEqual(result["observations"], 0)

    def test_procurement_recommendation_adds_safety_stock_from_forecast_error(self):
        result = procurement_recommendation(
            next_forecast=100,
            stock=80,
            lead_time_days=30,
            forecast_mae=10,
        )
        self.assertEqual(result["lead_demand"], 100.0)
        self.assertEqual(result["safety_stock"], 12.8)
        self.assertEqual(result["order_quantity"], 32.8)
        self.assertEqual(result["confidence"], 90.0)

    def test_procurement_recommendation_marks_unknown_accuracy(self):
        result = procurement_recommendation(
            next_forecast=100,
            stock=80,
            lead_time_days=30,
            forecast_mae=None,
        )
        self.assertIsNone(result["confidence"])
        self.assertEqual(result["confidence_level"], "недостатньо даних")


if __name__ == "__main__":
    unittest.main()
