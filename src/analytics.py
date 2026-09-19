"""Reusable operational analytics for the fulfillment case study."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


PROCESS_COLUMNS = {
    "Validation": "validation_time",
    "Inventory": "inventory_time",
    "Payment": "payment_time",
    "Picking & Packing": "picking_time",
    "Quality Control": "qc_time",
    "Shipping": "shipping_time",
}

REQUIRED_COLUMNS = {
    "order_id",
    "order_date",
    *PROCESS_COLUMNS.values(),
    "total_cycle_time_minutes",
    "total_errors",
    "rework_required",
}


@dataclass(frozen=True)
class DataQualitySummary:
    """Compact quality report for one order-state dataset."""

    rows: int
    duplicate_order_ids: int
    missing_cells: int
    invalid_cycle_times: int
    invalid_rework_flags: int


def validate_orders(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize an order-level fulfillment dataset."""
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    clean = frame.copy()
    clean["order_date"] = pd.to_datetime(clean["order_date"], errors="coerce")

    numeric_columns = [
        *PROCESS_COLUMNS.values(),
        "total_cycle_time_minutes",
        "total_errors",
        "rework_required",
    ]
    for column in numeric_columns:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")

    if clean["order_id"].isna().any():
        raise ValueError("order_id contains missing values")
    if clean["order_date"].isna().any():
        raise ValueError("order_date contains unparseable dates")
    return clean


def load_order_states(
    before_path: str | Path,
    after_path: str | Path,
) -> pd.DataFrame:
    """Load before/after CSVs into one tidy analytical table."""
    before = validate_orders(pd.read_csv(before_path))
    after = validate_orders(pd.read_csv(after_path))
    before.insert(0, "state", "Before")
    after.insert(0, "state", "After")
    return pd.concat([before, after], ignore_index=True)


def data_quality_summary(frame: pd.DataFrame) -> DataQualitySummary:
    """Measure common order-level data-quality issues."""
    clean = validate_orders(frame)
    return DataQualitySummary(
        rows=len(clean),
        duplicate_order_ids=int(clean["order_id"].duplicated().sum()),
        missing_cells=int(clean.isna().sum().sum()),
        invalid_cycle_times=int((clean["total_cycle_time_minutes"] <= 0).sum()),
        invalid_rework_flags=int((~clean["rework_required"].isin([0, 1])).sum()),
    )


def state_kpis(frame: pd.DataFrame) -> pd.DataFrame:
    """Return business KPIs by before/after state."""
    if "state" not in frame.columns:
        raise ValueError("frame must contain a state column")
    clean = validate_orders(frame.drop(columns=["state"])).assign(
        state=frame["state"].to_numpy()
    )

    records: list[dict] = []
    for state, group in clean.groupby("state", sort=False):
        cycle = group["total_cycle_time_minutes"]
        records.append(
            {
                "State": state,
                "Orders": len(group),
                "Average Cycle Time": float(cycle.mean()),
                "Median Cycle Time": float(cycle.median()),
                "P90 Cycle Time": float(cycle.quantile(0.90)),
                "Error Rate": float((group["total_errors"] > 0).mean()),
                "Rework Rate": float((group["rework_required"] > 0).mean()),
                "Orders / 8h Day": float(480.0 / cycle.mean()),
                "Monthly Capacity": float(480.0 / cycle.mean() * 22),
            }
        )
    return pd.DataFrame(records)


def improvement_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Compare core before/after KPIs using direction-aware improvement."""
    kpis = state_kpis(frame).set_index("State")
    if not {"Before", "After"}.issubset(kpis.index):
        raise ValueError("both Before and After states are required")

    definitions = [
        ("Average Cycle Time", "lower"),
        ("P90 Cycle Time", "lower"),
        ("Error Rate", "lower"),
        ("Rework Rate", "lower"),
        ("Orders / 8h Day", "higher"),
        ("Monthly Capacity", "higher"),
    ]
    rows = []
    for metric, direction in definitions:
        before = float(kpis.loc["Before", metric])
        after = float(kpis.loc["After", metric])
        if before == 0:
            change = np.nan
        elif direction == "lower":
            change = (before - after) / abs(before)
        else:
            change = (after - before) / abs(before)
        rows.append(
            {
                "Metric": metric,
                "Before": before,
                "After": after,
                "Improvement": change,
                "Preferred Direction": direction,
            }
        )
    return pd.DataFrame(rows)


def process_step_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Compare average process-step time and contribution by state."""
    if "state" not in frame.columns:
        raise ValueError("frame must contain a state column")

    rows: list[dict] = []
    for state, group in frame.groupby("state", sort=False):
        for step, column in PROCESS_COLUMNS.items():
            average = float(group[column].mean())
            rows.append(
                {
                    "State": state,
                    "Process Step": step,
                    "Average Minutes": average,
                    "Share of Cycle Time": float(
                        average / group["total_cycle_time_minutes"].mean()
                    ),
                }
            )
    summary = pd.DataFrame(rows)
    pivot = summary.pivot(
        index="Process Step",
        columns="State",
        values="Average Minutes",
    )
    if {"Before", "After"}.issubset(pivot.columns):
        summary = summary.merge(
            (
                pivot["Before"] - pivot["After"]
            ).rename("Minutes Saved").reset_index(),
            on="Process Step",
            how="left",
        )
    return summary


def bottleneck_pareto(frame: pd.DataFrame, state: str = "Before") -> pd.DataFrame:
    """Rank process steps by their contribution to average cycle time."""
    subset = frame.loc[frame["state"] == state]
    if subset.empty:
        raise ValueError(f"no rows found for state {state!r}")

    values = pd.Series(
        {
            step: float(subset[column].mean())
            for step, column in PROCESS_COLUMNS.items()
        }
    ).sort_values(ascending=False)

    result = values.rename("Average Minutes").reset_index()
    result = result.rename(columns={"index": "Process Step"})
    result["Share"] = result["Average Minutes"] / result["Average Minutes"].sum()
    result["Cumulative Share"] = result["Share"].cumsum()
    result["Rank"] = np.arange(1, len(result) + 1)
    return result


def daily_operating_trend(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate order-level data into repeatable daily operational KPIs."""
    clean = frame.copy()
    clean["order_date"] = pd.to_datetime(clean["order_date"])
    trend = (
        clean.groupby(["state", "order_date"], as_index=False)
        .agg(
            Orders=("order_id", "size"),
            Average_Cycle_Time=("total_cycle_time_minutes", "mean"),
            P90_Cycle_Time=("total_cycle_time_minutes", lambda s: s.quantile(0.90)),
            Error_Rate=("total_errors", lambda s: (s > 0).mean()),
            Rework_Rate=("rework_required", lambda s: (s > 0).mean()),
        )
        .sort_values(["state", "order_date"])
    )
    trend["Cycle_Time_7D_Avg"] = (
        trend.groupby("state")["Average_Cycle_Time"]
        .transform(lambda s: s.rolling(7, min_periods=1).mean())
    )
    return trend


def financial_impact(
    frame: pd.DataFrame,
    *,
    monthly_order_volume: int = 1000,
    hourly_labor_cost: float = 25.0,
) -> dict[str, float]:
    """Estimate labor-capacity impact from the observed cycle-time difference."""
    if monthly_order_volume < 0 or hourly_labor_cost < 0:
        raise ValueError("volume and labor cost must be non-negative")

    kpis = state_kpis(frame).set_index("State")
    before = float(kpis.loc["Before", "Average Cycle Time"])
    after = float(kpis.loc["After", "Average Cycle Time"])
    minutes_saved = before - after
    monthly_hours = minutes_saved / 60.0 * monthly_order_volume
    monthly_savings = monthly_hours * hourly_labor_cost
    return {
        "minutes_saved_per_order": minutes_saved,
        "monthly_hours_saved": monthly_hours,
        "monthly_cost_savings": monthly_savings,
        "annual_cost_savings": monthly_savings * 12.0,
    }


def top_exception_orders(
    frame: pd.DataFrame,
    *,
    state: str = "Before",
    limit: int = 10,
) -> pd.DataFrame:
    """Surface high-cycle-time/error/rework orders using percentile ranks."""
    subset = frame.loc[frame["state"] == state].copy()
    if subset.empty:
        raise ValueError(f"no rows found for state {state!r}")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    subset["Cycle Percentile"] = subset["total_cycle_time_minutes"].rank(
        pct=True,
        method="average",
    )
    subset["Exception Score"] = (
        0.60 * subset["Cycle Percentile"]
        + 0.25 * (subset["total_errors"] > 0).astype(float)
        + 0.15 * (subset["rework_required"] > 0).astype(float)
    )
    return (
        subset.sort_values("Exception Score", ascending=False)
        .head(limit)
        [
            [
                "order_id",
                "order_date",
                "total_cycle_time_minutes",
                "total_errors",
                "rework_required",
                "Cycle Percentile",
                "Exception Score",
            ]
        ]
        .reset_index(drop=True)
    )
