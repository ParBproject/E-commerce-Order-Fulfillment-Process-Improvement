from __future__ import annotations

from pathlib import Path

import pytest

from bayline.analyze import connect, export
from bayline.generate import simulate, write_tables
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


def test_window_rank_is_top_eight(con):
    worst = con.execute(
        "SELECT facility_id, period, cycle_rank FROM worst_cartons ORDER BY facility_id, period, cycle_rank"
    ).fetchdf()
    for _, group in worst.groupby(["facility_id", "period"], sort=False):
        assert group["cycle_rank"].tolist() == list(range(1, 9))
    # order_id is the tie-break, so a shared cycle time cannot pull in a 9th carton.
    overflow = con.execute(
        """
        WITH ranked AS (
            SELECT RANK() OVER (
                PARTITION BY facility_id, period
                ORDER BY cycle_minutes DESC, order_id
            ) AS cycle_rank
            FROM order_enriched
        )
        SELECT COUNT(*) FROM ranked WHERE cycle_rank <= 8
        """
    ).fetchone()[0]
    assert overflow == 8 * 3 * 2


def test_analysis_sql_has_join_and_window():
    sql = (SQL / "analysis.sql").read_text().upper()
    assert "JOIN" in sql
    assert "RANK() OVER" in sql
    assert "QUANTILE_CONT" in sql
    assert "LAG(" in sql


def test_simulate_is_repeatable():
    first = simulate()
    second = simulate()
    for name in first:
        left = first[name].reset_index(drop=True)
        right = second[name].reset_index(drop=True)
        assert left.equals(right), name


def test_sla_flag_matches_stored_cycle(tables):
    orders = tables["fact_orders"]
    exceptions = tables["fact_exceptions"]
    expected = (orders["cycle_minutes"] > 120).astype(int)
    assert orders["sla_miss_flag"].eq(expected).all()
    misses = exceptions[exceptions["exception_code"] == "missed_sla"]
    assert misses["minutes_added"].gt(0).all()
    assert set(misses["order_id"]) == set(orders.loc[orders["sla_miss_flag"] == 1, "order_id"])
    # The pre-round sum used to flag this on-gate carton and attach a 0-minute miss.
    boundary = orders.loc[orders["order_id"] == "BL-12661"].iloc[0]
    assert boundary["cycle_minutes"] == 120.0
    assert boundary["sla_miss_flag"] == 0


def test_seed_preserves_cycle_times(tables):
    # SLA flag fix must not reshuffle dwell. This is the seed-42 cycle total.
    assert tables["fact_orders"]["cycle_minutes"].sum() == pytest.approx(449_856.4, abs=0.05)
    assert len(tables["fact_orders"]) == 4524


@pytest.fixture(scope="session")
def payload(tables):
    return export()


def test_touch_labor_has_no_fanout_or_averaged_rate(con):
    counts = con.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM order_enriched),
            (SELECT COUNT(*) FROM fact_orders),
            (SELECT COUNT(*) FROM step_enriched),
            (SELECT COUNT(*) FROM fact_order_steps),
            (SELECT COUNT(*) FROM order_enriched WHERE touch_hours IS NULL)
        """
    ).fetchone()
    assert counts == (4524, 4524, 27144, 27144, 0)
    direct = con.execute(
        """
        SELECT
            period,
            ROUND(SUM(touch_hours), 1) AS hours,
            ROUND(SUM(touch_hours * labor_rate), 0) AS usd,
            ROUND(SUM(cycle_minutes) / 60.0 * AVG(labor_rate), 0) AS averaged_cycle_usd,
            ROUND(SUM(dwell_hours), 1) AS step_hours
        FROM (
            SELECT
                o.period,
                o.touch_hours,
                o.labor_rate,
                o.cycle_minutes,
                (
                    SELECT SUM(s.dwell_minutes) / 60.0
                    FROM fact_order_steps s
                    WHERE s.order_id = o.order_id
                      AND s.step_id IN ('slot_locate', 'pick', 'pack', 'qc')
                ) AS dwell_hours
            FROM order_enriched o
        )
        GROUP BY period
        ORDER BY period
        """
    ).fetchdf()
    kpi = con.execute(
        "SELECT period, labor_hours, loaded_labor_usd FROM kpi_period ORDER BY period"
    ).fetchdf()
    for left, right in zip(kpi.itertuples(index=False), direct.itertuples(index=False), strict=True):
        assert left.labor_hours == pytest.approx(right.hours, abs=0.05)
        assert left.loaded_labor_usd == pytest.approx(right.usd, abs=0.5)
        assert left.labor_hours == pytest.approx(right.step_hours, abs=0.05)
        assert abs(left.loaded_labor_usd - right.averaged_cycle_usd) > 100


def test_weeks_stay_on_local_mondays(con, payload):
    shifted = con.execute(
        """
        SELECT COUNT(*) FROM order_enriched
        WHERE isodow(week_start) <> 1
           OR CAST(order_date AS DATE) < week_start
           OR CAST(order_date AS DATE) >= week_start + INTERVAL 7 DAY
        """
    ).fetchone()[0]
    assert shifted == 0
    weeks = payload["weekly_network"]
    assert weeks[0]["week_start"] == "2025-01-06"
    assert weeks[0]["prior_median"] is None
    assert all("T" not in row["week_start"] for row in weeks)
    for previous, row in zip(weeks, weeks[1:]):
        assert row["prior_median"] == previous["median_cycle"]


def test_payback_uses_facility_touch_rates(con, payload):
    rows = con.execute(
        """
        SELECT facility_id, period, COUNT(*)::DOUBLE AS n,
               SUM(touch_hours) AS hours, ANY_VALUE(labor_rate) AS rate
        FROM order_enriched
        GROUP BY facility_id, period
        """
    ).fetchdf()
    days_per_week, n_weeks, working_days, cost = con.execute(
        """
        SELECT
            (SELECT COUNT(DISTINCT order_date)::DOUBLE / COUNT(DISTINCT week_start) FROM order_enriched),
            (SELECT COUNT(DISTINCT week_start) FROM order_enriched),
            (SELECT value FROM dim_assumption WHERE assumption_id = 'working_days_month'),
            (SELECT value FROM dim_assumption WHERE assumption_id = 'pilot_implementation_cost')
        """
    ).fetchone()
    weighted_usd = 0.0
    total_orders = 0.0
    for _, group in rows.groupby("facility_id"):
        base = group.loc[group["period"] == "baseline"].iloc[0]
        pilot = group.loc[group["period"] == "pilot"].iloc[0]
        saved = float(base.hours) / float(base.n) - float(pilot.hours) / float(pilot.n)
        weight = float(base.n) + float(pilot.n)
        weighted_usd += saved * float(base.rate) * weight
        total_orders += weight
    monthly_orders = (total_orders / float(n_weeks)) * (float(working_days) / float(days_per_week))
    expected = round(float(cost) / (weighted_usd / total_orders * monthly_orders), 1)
    assert payload["money"]["payback_months_observed"] == pytest.approx(expected, abs=0.05)
    # Full-cycle hours priced at the blended rate paid back in 4.6 months.
    assert payload["money"]["payback_months_observed"] > 4.6
    assert days_per_week == pytest.approx(6.0)
    assert n_weeks == 16


def test_published_scorecard(payload):
    kpi = {row["period"]: row for row in payload["kpi_period"]}
    cells = {(row["cell"], row["period"]): row for row in payload["sla_cells"]}
    assert kpi["baseline"]["orders"] == 2220
    assert kpi["pilot"]["orders"] == 2304
    assert kpi["baseline"]["median_cycle"] == pytest.approx(109.7)
    assert kpi["pilot"]["median_cycle"] == pytest.approx(84.6)
    assert kpi["baseline"]["p90_cycle"] == pytest.approx(147.3)
    assert kpi["pilot"]["p90_cycle"] == pytest.approx(111.4)
    assert kpi["baseline"]["sla_miss_pct"] == pytest.approx(34.2)
    assert kpi["pilot"]["sla_miss_pct"] == pytest.approx(5.4)
    assert kpi["baseline"]["rework_rate_pct"] == pytest.approx(17.2)
    assert kpi["pilot"]["rework_rate_pct"] == pytest.approx(10.8)
    assert cells[("Fontana night", "baseline")]["sla_miss_pct"] == pytest.approx(79.9)
    assert cells[("Fontana night", "pilot")]["sla_miss_pct"] == pytest.approx(15.6)
    assert payload["money"]["window_usd"] == pytest.approx(22885, abs=0.5)
    assert payload["money"]["blended_labor_rate"] == pytest.approx(28.27)
    assert payload["tests"]["bootstrap"]["ci95_low"] == pytest.approx(23.5)
    assert payload["tests"]["bootstrap"]["ci95_high"] == pytest.approx(26.5)
    assert payload["tests"]["mannwhitney"]["p_value"] < 0.001
    pick = next(row for row in payload["step_profile"] if row["step_id"] == "pick")
    assert pick["baseline_share_pct"] == pytest.approx(47.5)


def test_bootstrap_interval_is_repeatable(payload):
    again = export()
    assert again["tests"]["bootstrap"] == payload["tests"]["bootstrap"]


def test_cost_and_sla_come_from_assumptions(con, payload):
    sla, cost, rate = con.execute(
        """
        SELECT
            MAX(CASE WHEN assumption_id = 'sla_minutes' THEN value END),
            MAX(CASE WHEN assumption_id = 'pilot_implementation_cost' THEN value END),
            MAX(CASE WHEN assumption_id = 'hourly_loaded_labor' THEN value END)
        FROM dim_assumption
        """
    ).fetchone()
    assert payload["sla_minutes"] == sla
    assert payload["implementation_cost"] == cost
    assert rate is None


def test_export_payload_is_internally_consistent(payload):
    assert payload["tests"]["mannwhitney"]["p_value"] < 0.01
    assert payload["tests"]["bootstrap"]["ci95_low"] > 0
    kpis = {row["period"]: row for row in payload["kpi_period"]}
    assert kpis["pilot"]["sla_miss_pct"] < kpis["baseline"]["sla_miss_pct"]
    assert Path(DATA / "fact_orders.csv").exists()
    volumes = [row["monthly_orders"] for row in payload["sensitivity"]]
    dollars = [row["usd_year"] for row in payload["sensitivity"]]
    assert volumes == sorted(volumes)
    assert dollars == sorted(dollars)
