"""Transparent domain analytics for construction-material sales."""

from __future__ import annotations

from collections import defaultdict
from math import sqrt


def linear_trend(values: list[float]) -> tuple[float, float]:
    """Return intercept and slope of least-squares trend."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    denominator = sum((x - x_mean) ** 2 for x in range(n))
    slope = (
        0.0
        if denominator == 0
        else sum((x - x_mean) * (y - y_mean) for x, y in enumerate(values)) / denominator
    )
    return y_mean - slope * x_mean, slope


def demand_forecast(monthly: list[tuple[str, float]], horizon: int = 3) -> list[dict]:
    """Forecast with linear trend multiplied by calendar-month seasonal factors."""
    if not monthly or horizon < 1:
        return []
    values = [value for _, value in monthly]
    intercept, slope = linear_trend(values)
    seasonal: dict[int, list[float]] = defaultdict(list)
    for index, (period, value) in enumerate(monthly):
        baseline = max(0.0001, intercept + slope * index)
        seasonal[int(period[5:7])].append(value / baseline)
    factor = {month: sum(items) / len(items) for month, items in seasonal.items()}
    last_year, last_month = map(int, monthly[-1][0].split("-")[:2])
    result = []
    for step in range(1, horizon + 1):
        month_number = (last_month - 1 + step) % 12 + 1
        year = last_year + (last_month - 1 + step) // 12
        estimate = max(
            0,
            (intercept + slope * (len(values) + step - 1)) * factor.get(month_number, 1.0),
        )
        result.append({"period": f"{year:04d}-{month_number:02d}", "quantity": round(estimate, 2)})
    return result


def seasonal_naive_forecast(monthly: list[tuple[str, float]], period: str) -> float | None:
    """Return demand of the same calendar month one year earlier, if it is known.

    This is the standard benchmark for seasonal data: a forecasting model is
    only useful when it beats it.
    """
    year, month = int(period[:4]), int(period[5:7])
    return dict(monthly).get(f"{year - 1:04d}-{month:02d}")


def _error_metrics(errors: list[float], actuals: list[float]) -> dict:
    """MAE and RMSE keep the material's unit; MAPE is a percentage over non-zero actuals."""
    if not errors:
        return {"observations": 0, "mae": None, "rmse": None, "mape": None}
    percentage_errors = [
        abs(error) / abs(actual) * 100 for error, actual in zip(errors, actuals) if actual
    ]
    return {
        "observations": len(errors),
        "mae": round(sum(abs(error) for error in errors) / len(errors), 2),
        "rmse": round(sqrt(sum(error**2 for error in errors) / len(errors)), 2),
        "mape": round(sum(percentage_errors) / len(percentage_errors), 2)
        if percentage_errors
        else None,
    }


def forecast_accuracy(monthly: list[tuple[str, float]], min_train_periods: int = 6) -> dict:
    """Evaluate one-step rolling forecasts against known historical demand.

    The result also contains a ``baseline`` block that scores the seasonal-naive
    forecast on exactly the same months where it is available (i.e. where the
    previous year is known), so both models are compared on equal terms.
    ``gain_pct`` is the MAE reduction of the model relative to the baseline;
    a positive value means the model is better.
    """
    empty = {
        **_error_metrics([], []),
        "baseline": {**_error_metrics([], []), "model_mae": None, "gain_pct": None},
    }
    if len(monthly) <= min_train_periods:
        return empty
    errors: list[float] = []
    actuals: list[float] = []
    paired_model_errors: list[float] = []
    baseline_errors: list[float] = []
    paired_actuals: list[float] = []
    for point in range(min_train_periods, len(monthly)):
        period, actual = monthly[point]
        error = demand_forecast(monthly[:point], horizon=1)[0]["quantity"] - actual
        errors.append(error)
        actuals.append(actual)
        naive = seasonal_naive_forecast(monthly[:point], period)
        if naive is not None:
            paired_model_errors.append(error)
            baseline_errors.append(naive - actual)
            paired_actuals.append(actual)
    baseline = _error_metrics(baseline_errors, paired_actuals)
    model_mae = _error_metrics(paired_model_errors, paired_actuals)["mae"]
    gain = None
    if baseline["mae"]:
        gain = round((baseline["mae"] - model_mae) / baseline["mae"] * 100, 2)
    return {
        **_error_metrics(errors, actuals),
        "baseline": {**baseline, "model_mae": model_mae, "gain_pct": gain},
    }


# Expert weights of the CPRI components: demand over lead time (D), demand
# volatility (V), lead time (L) and seasonal acceleration (S).
CPRI_WEIGHTS: dict[str, float] = {
    "demand": 0.40,
    "volatility": 0.25,
    "lead": 0.20,
    "seasonality": 0.15,
}


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    """Check that CPRI weights are complete, non-negative and sum to one."""
    if set(weights) != set(CPRI_WEIGHTS):
        raise ValueError(
            f"Ваги CPRI мають містити рівно такі компоненти: {', '.join(CPRI_WEIGHTS)}."
        )
    if any(value < 0 for value in weights.values()):
        raise ValueError("Ваги CPRI не можуть бути від'ємними.")
    if abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("Сума ваг CPRI має дорівнювати 1.")
    return dict(weights)


def shortage_risk(
    monthly_values: list[float],
    stock: float,
    lead_time_days: int,
    next_forecast: float | None = None,
    weights: dict[str, float] | None = None,
) -> dict:
    """Calculate seasonality-adaptive Construction Procurement Risk Index (CPRI).

    ``weights`` default to the expert weights in ``CPRI_WEIGHTS``.
    """
    weights = validate_weights(weights) if weights is not None else CPRI_WEIGHTS
    if not monthly_values:
        return {
            "score": 0,
            "level": "низький",
            "demand_component": 0,
            "volatility_component": 0,
            "lead_component": 0,
            "seasonality_component": 0,
        }
    mean = sum(monthly_values) / len(monthly_values)
    deviation = sqrt(sum((v - mean) ** 2 for v in monthly_values) / len(monthly_values))
    expected_lead_demand = (
        (next_forecast if next_forecast is not None else mean) * lead_time_days / 30
    )
    demand = min(1, expected_lead_demand / max(stock, 1))
    volatility = min(1, deviation / max(mean, 1))
    lead = min(1, lead_time_days / 30)
    seasonality = min(1, max(0, (next_forecast or mean) / max(mean, 1) - 1))
    score = round(
        100
        * (
            weights["demand"] * demand
            + weights["volatility"] * volatility
            + weights["lead"] * lead
            + weights["seasonality"] * seasonality
        ),
        1,
    )
    level = "високий" if score >= 70 else "середній" if score >= 40 else "низький"
    return {
        "score": score,
        "level": level,
        "demand_component": round(demand, 3),
        "volatility_component": round(volatility, 3),
        "lead_component": round(lead, 3),
        "seasonality_component": round(seasonality, 3),
    }


def manager_scores(rows: list[dict]) -> list[dict]:
    """Rank managers by normalized revenue, deals, and average order value."""
    totals: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "deals": 0})
    for row in rows:
        item = totals[row["manager"]]
        item["revenue"] += row["quantity"] * row["unit_price"]
        item["deals"] += 1
    if not totals:
        return []
    max_revenue = max(item["revenue"] for item in totals.values()) or 1
    max_deals = max(item["deals"] for item in totals.values()) or 1
    max_average = max(item["revenue"] / item["deals"] for item in totals.values()) or 1
    result = []
    for manager, item in totals.items():
        average = item["revenue"] / item["deals"]
        score = 100 * (
            0.5 * item["revenue"] / max_revenue
            + 0.3 * item["deals"] / max_deals
            + 0.2 * average / max_average
        )
        result.append(
            {
                "manager": manager,
                "revenue": round(item["revenue"], 2),
                "deals": item["deals"],
                "average_check": round(average, 2),
                "score": round(score, 1),
            }
        )
    return sorted(result, key=lambda item: item["score"], reverse=True)
