from pathlib import Path

import pandas as pd
import pytest

from src.analytics import (
    bottleneck_pareto,
    data_quality_summary,
    financial_impact,
    improvement_table,
    load_order_states,
    state_kpis,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def orders():
    return load_order_states(
        ROOT / "before_state_data.csv",
        ROOT / "after_state_data.csv",
    )


def test_state_kpis_include_before_and_after(orders):
    kpis = state_kpis(orders)
    assert set(kpis["State"]) == {"Before", "After"}
    assert (kpis["Orders"] > 0).all()


def test_after_cycle_time_is_lower_in_case_study(orders):
    kpis = state_kpis(orders).set_index("State")
    assert (
        kpis.loc["After", "Average Cycle Time"]
        < kpis.loc["Before", "Average Cycle Time"]
    )


def test_improvement_table_has_positive_cycle_time_improvement(orders):
    table = improvement_table(orders).set_index("Metric")
    assert table.loc["Average Cycle Time", "Improvement"] > 0


def test_pareto_is_ranked_and_cumulative(orders):
    pareto = bottleneck_pareto(orders, "Before")
    assert pareto["Rank"].tolist() == list(range(1, len(pareto) + 1))
    assert pareto["Cumulative Share"].is_monotonic_increasing
    assert pareto["Cumulative Share"].iloc[-1] == pytest.approx(1.0)


def test_financial_impact_matches_observed_direction(orders):
    impact = financial_impact(
        orders,
        monthly_order_volume=1000,
        hourly_labor_cost=25.0,
    )
    assert impact["minutes_saved_per_order"] > 0
    assert impact["annual_cost_savings"] > 0


def test_data_quality_detects_duplicate_order_ids():
    frame = pd.read_csv(ROOT / "before_state_data.csv")
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    summary = data_quality_summary(duplicate)
    assert summary.duplicate_order_ids == 1
