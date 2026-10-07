# Forecast pipeline: evaluates demand history, reorder quantities and anomaly indicators.
# Metrics describe prediction error and model limitations; results remain advisory.
# Django stores the analysis and human decision; purchasing handles any later real order.
"""reproducible baselines, holdout errors and advisory decisions."""

import math
from statistics import mean, pstdev

import sklearn
from pydantic import BaseModel, ConfigDict, Field
from sklearn.ensemble import IsolationForest

MODEL_VERSION = "moving-average7-margin20-isolation-v1"


class MarginRow(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str = Field(max_length=80)
    revenue: float = Field(ge=0, le=1e16)
    cost: float = Field(ge=0, le=1e16)
    currency: str = Field(pattern="^(DZD|EUR|USD)$")


class ForecastInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    # Django constructs consecutive daily buckets, including days with no shipments.
    daily_demand: list[float] = Field(min_length=28, max_length=90)
    available: float = Field(ge=-1e12, le=1e12)
    minimum_stock: float = Field(ge=0, le=1e12)
    lead_time_days: int = Field(ge=1, le=90)
    horizon_days: int = Field(ge=1, le=90)
    allows_decimals: bool
    margins: list[MarginRow] = Field(default_factory=list, max_length=200)


def analyze(data):
    values = data.daily_demand
    if any(not math.isfinite(value) or value < 0 or value > 1e12 for value in values):
        raise ValueError("Demand must contain bounded nonnegative finite quantities.")
    # Last seven days are a rolling-origin holdout. Each prediction uses only its past.
    errors = [abs(values[i] - mean(values[i - 7 : i])) for i in range(len(values) - 7, len(values))]
    actual = sum(values[-7:])
    daily = mean(values[-7:])
    target = daily * data.lead_time_days + data.minimum_stock
    shortage = max(0, target - data.available)
    reorder = math.ceil(shortage * (10000 if data.allows_decimals else 1)) / (
        10000 if data.allows_decimals else 1
    )
    # IsolationForest is compared against a deterministic rule, not treated as truth.
    train = [[value] for value in values[:-7]]
    model = IsolationForest(random_state=42, n_estimators=100, contamination="auto", n_jobs=1)
    model.fit(train)
    predictions = model.predict([[value] for value in values[-7:]])
    center, spread = mean(values[:-7]), pstdev(values[:-7])
    anomalies = [
        {
            "day_index": len(values) - 7 + i,
            "demand": value,
            "isolation_forest": bool(predictions[i] == -1),
            "rule_spike": bool(value > center + 3 * spread),
        }
        for i, value in enumerate(values[-7:])
    ]
    margin_flags = []
    for row in data.margins:
        percent = (row.revenue - row.cost) / row.revenue * 100 if row.revenue else None
        if percent is None or percent < 20:
            margin_flags.append(
                {
                    "line_id": row.id,
                    "currency": row.currency,
                    "margin_percent": round(percent, 2) if percent is not None else None,
                }
            )
    return {
        "model_version": MODEL_VERSION,
        "sklearn_version": sklearn.__version__,
        "daily_forecast": round(daily, 4),
        "horizon_forecast": round(daily * data.horizon_days, 4),
        "mae": round(mean(errors), 4),
        "wape_percent": round(sum(errors) / actual * 100, 2) if actual else None,
        "holdout_days": 7,
        "reorder_quantity": reorder,
        "available_used": data.available,
        "margin_flags": margin_flags,
        "anomaly_comparison": anomalies,
        "limitations": (
            "Shipment demand can be censored by stockouts. "
            "No seasonality, open purchase orders or automatic purchasing. "
            "WAPE is undefined when holdout demand is zero."
        ),
    }
