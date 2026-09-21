from __future__ import annotations

from pathlib import Path

import pytest

from bayline.analyze import connect, export
from bayline.generate import write_tables
from bayline.paths import DATA, SQL


@pytest.fixture(scope="session")
def tables():
    return write_tables()


@pytest.fixture(scope="session")
def con(tables):
    connection = connect()
    yield connection
    connection.close()


def test_star_schema_keys(tables):
    orders = tables["fact_orders"]
    steps = tables["fact_order_steps"]
    assert orders["order_id"].is_unique
    assert set(steps["order_id"]) <= set(orders["order_id"])
    assert steps.groupby("order_id").size().min() == 6
    assert (steps["dwell_minutes"] > 0).all()
    assert (orders["cycle_minutes"] > 0).all()
    assert set(orders["facility_id"]) == {"AUS-01", "EWR-07", "FNT-12"}
    assert set(orders["period"]) == {"baseline", "pilot"}


def test_enough_volume_for_cuts(tables):
    orders = tables["fact_orders"]
    counts = orders.groupby(["period", "facility_id", "shift"]).size()
    assert counts.min() >= 20
    assert len(orders) >= 1200


def test_pilot_improves_median(tables):
    med = tables["fact_orders"].groupby("period")["cycle_minutes"].median()
    assert med["pilot"] < med["baseline"] * 0.85


def test_fontana_night_was_the_problem(tables):
    orders = tables["fact_orders"]
    cell = orders[(orders["facility_id"] == "FNT-12") & (orders["shift"] == "Night")]
    rest = orders[~((orders["facility_id"] == "FNT-12") & (orders["shift"] == "Night"))]
    before_cell = cell.loc[cell["period"] == "baseline", "cycle_minutes"].median()
    before_rest = rest.loc[rest["period"] == "baseline", "cycle_minutes"].median()
    after_cell = cell.loc[cell["period"] == "pilot", "cycle_minutes"].median()
    assert before_cell > before_rest
    assert after_cell < before_cell * 0.8


def test_sql_scorecard_matches_pandas(con, tables):
    kpi = con.execute("SELECT period, median_cycle, orders FROM kpi_period").fetchdf()
    pandas_med = tables["fact_orders"].groupby("period")["cycle_minutes"].median().round(1)
    pandas_n = tables["fact_orders"].groupby("period").size()
    for _, row in kpi.iterrows():
        assert row["median_cycle"] == pytest.approx(pandas_med[row["period"]], abs=0.11)
        assert int(row["orders"]) == int(pandas_n[row["period"]])


def test_step_profile_pick_is_largest_baseline_share(con):
    steps = con.execute("SELECT * FROM step_profile ORDER BY baseline_share_pct DESC").fetchdf()
    assert steps.iloc[0]["step_id"] == "pick"
    assert (steps["minutes_recovered"] >= 0).all()


def test_window_rank_is_dense_within_facility(con):
    worst = con.execute("SELECT facility_id, period, cycle_rank FROM worst_cartons").fetchdf()
    grouped = worst.groupby(["facility_id", "period"]).size()
    assert (grouped == 8).all()


def test_analysis_sql_has_join_and_window():
    sql = (SQL / "analysis.sql").read_text().upper()
    assert "JOIN" in sql
    assert "RANK() OVER" in sql
    assert "QUANTILE_CONT" in sql
    assert "LAG(" in sql


def test_export_payload_is_internally_consistent(tables):
    payload = export()
    assert payload["tests"]["mannwhitney"]["p_value"] < 0.01
    assert payload["tests"]["bootstrap"]["ci95_low"] > 0
    kpis = {row["period"]: row for row in payload["kpi_period"]}
    assert kpis["pilot"]["sla_miss_pct"] < kpis["baseline"]["sla_miss_pct"]
    assert Path(DATA / "fact_orders.csv").exists()
    volumes = [row["monthly_orders"] for row in payload["sensitivity"]]
    dollars = [row["usd_year"] for row in payload["sensitivity"]]
    assert volumes == sorted(volumes)
    assert dollars == sorted(dollars)
