"""Transparent domain analytics for construction-material sales."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt


def linear_trend(values: list[float]) -> tuple[float, float]:
    """Return intercept and slope of least-squares trend."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    denominator = sum((x - x_mean) ** 2 for x in range(n))
    slope = 0.0 if denominator == 0 else sum((x - x_mean) * (y - y_mean) for x, y in enumerate(values)) / denominator
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
        estimate = max(0, (intercept + slope * (len(values) + step - 1)) * factor.get(month_number, 1.0))
        result.append({"period": f"{year:04d}-{month_number:02d}", "quantity": round(estimate, 2)})
    return result


def shortage_risk(monthly_values: list[float], stock: float, lead_time_days: int, next_forecast: float | None = None) -> dict:
    """Calculate seasonality-adaptive Construction Procurement Risk Index (CPRI)."""
    if not monthly_values:
        return {"score": 0, "level": "низький", "demand_component": 0, "volatility_component": 0, "lead_component": 0, "seasonality_component": 0}
    mean = sum(monthly_values) / len(monthly_values)
    deviation = sqrt(sum((v - mean) ** 2 for v in monthly_values) / len(monthly_values))
    expected_lead_demand = (next_forecast if next_forecast is not None else mean) * lead_time_days / 30
    demand = min(1, expected_lead_demand / max(stock, 1))
    volatility = min(1, deviation / max(mean, 1))
    lead = min(1, lead_time_days / 30)
    seasonality = min(1, max(0, (next_forecast or mean) / max(mean, 1) - 1))
    score = round(100 * (0.40 * demand + 0.25 * volatility + 0.20 * lead + 0.15 * seasonality), 1)
    level = "високий" if score >= 70 else "середній" if score >= 40 else "низький"
    return {"score": score, "level": level, "demand_component": round(demand, 3), "volatility_component": round(volatility, 3), "lead_component": round(lead, 3), "seasonality_component": round(seasonality, 3)}


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
        score = 100 * (0.5 * item["revenue"] / max_revenue + 0.3 * item["deals"] / max_deals + 0.2 * average / max_average)
        result.append({"manager": manager, "revenue": round(item["revenue"], 2), "deals": item["deals"], "average_check": round(average, 2), "score": round(score, 1)})
    return sorted(result, key=lambda item: item["score"], reverse=True)
