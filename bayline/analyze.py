"""Run the Bayline SQL marts, statistical tests, and dashboard export."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from bayline.paths import DASHBOARD, DATA, SQL


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    for table in (
        "dim_facility",
        "dim_step",
        "dim_assumption",
        "fact_orders",
        "fact_order_steps",
        "fact_exceptions",
    ):
        path = DATA / f"{table}.csv"
        con.execute(
            f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto(?, HEADER=TRUE)",
            [str(path)],
        )
    con.execute((SQL / "analysis.sql").read_text())
    return con


def _iso_if_date(value):
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _records(con: duckdb.DuckDBPyConnection, table: str) -> list[dict]:
    frame = con.execute(f"SELECT * FROM {table}").fetchdf()
    out = frame.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
        elif out[col].dtype == object:
            out[col] = out[col].map(_iso_if_date)
    return json.loads(out.to_json(orient="records"))


def _assumption(con: duckdb.DuckDBPyConnection, assumption_id: str) -> float:
    row = con.execute(
        "SELECT value FROM dim_assumption WHERE assumption_id = ?",
        [assumption_id],
    ).fetchone()
    if row is None or row[0] is None or pd.isna(row[0]):
        raise ValueError(f"dim_assumption.{assumption_id} has no value")
    return float(row[0])


def mannwhitney(baseline: np.ndarray, pilot: np.ndarray) -> dict:
    result = stats.mannwhitneyu(pilot, baseline, alternative="less")
    return {
        "u_statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "n_baseline": int(len(baseline)),
        "n_pilot": int(len(pilot)),
        "alternative": "pilot cycle times are smaller",
    }


def bootstrap_median_delta(
    baseline: np.ndarray,
    pilot: np.ndarray,
    draws: int = 2000,
) -> dict:
    # Reseed every call. A module-level generator made the second export drift.
    rng = np.random.default_rng(42)
    deltas = np.empty(draws)
    for i in range(draws):
        b = rng.choice(baseline, size=len(baseline), replace=True)
        p = rng.choice(pilot, size=len(pilot), replace=True)
        deltas[i] = np.median(b) - np.median(p)
    lo, hi = np.quantile(deltas, [0.025, 0.975])
    return {
        "median_delta_minutes": round(float(np.median(deltas)), 1),
        "ci95_low": round(float(lo), 1),
        "ci95_high": round(float(hi), 1),
        "draws": draws,
    }


def density(values: np.ndarray, bins: np.ndarray) -> list[dict]:
    counts, edges = np.histogram(values, bins=bins, density=True)
    out = []
    for i, count in enumerate(counts):
        out.append(
            {
                "x0": round(float(edges[i]), 1),
                "x1": round(float(edges[i + 1]), 1),
                "density": round(float(count), 5),
            }
        )
    return out


def touch_unit_economics(con: duckdb.DuckDBPyConnection) -> dict:
    """Touch-hour savings per carton, priced at each building's own rate.

    Weights are the observed carton counts, so a busier building contributes
    more. The month scale uses the calendar the generator actually ran
    (distinct operating dates per week) and dim_assumption.working_days_month.
    """
    working_days = _assumption(con, "working_days_month")
    days_per_week, n_weeks = con.execute(
        """
        SELECT
            COUNT(DISTINCT order_date)::DOUBLE / COUNT(DISTINCT week_start),
            COUNT(DISTINCT week_start)
        FROM order_enriched
        """
    ).fetchone()
    rows = con.execute(
        """
        SELECT
            facility_id,
            period,
            COUNT(*)::DOUBLE AS orders,
            SUM(touch_hours) AS touch_hours,
            ANY_VALUE(labor_rate) AS labor_rate
        FROM order_enriched
        GROUP BY facility_id, period
        """
    ).fetchdf()
    weighted_hours = 0.0
    weighted_usd = 0.0
    total_orders = 0.0
    for facility_id, group in rows.groupby("facility_id"):
        base = group.loc[group["period"] == "baseline"]
        pilot = group.loc[group["period"] == "pilot"]
        if len(base) != 1 or len(pilot) != 1:
            raise ValueError(f"{facility_id} is missing a baseline or pilot slice")
        base = base.iloc[0]
        pilot = pilot.iloc[0]
        hours_saved = float(base.touch_hours) / float(base.orders) - float(pilot.touch_hours) / float(pilot.orders)
        weight = float(base.orders) + float(pilot.orders)
        weighted_hours += hours_saved * weight
        weighted_usd += hours_saved * float(base.labor_rate) * weight
        total_orders += weight
    orders_per_week = total_orders / float(n_weeks)
    return {
        "hours_per_order": weighted_hours / total_orders,
        "usd_per_order": weighted_usd / total_orders,
        "monthly_orders_observed": orders_per_week * (working_days / float(days_per_week)),
        "days_per_week": float(days_per_week),
        "weeks": int(n_weeks),
    }


def volume_matched_touch_usd(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """Per-carton touch-time cut, priced at each building's rate.

    The in-window total subtracts raw hour sums, so a busier pilot shrinks
    the dollar figure. These two rows hold carton counts at the baseline
    mix and at the pilot mix instead.
    """
    rows = con.execute(
        """
        SELECT
            facility_id,
            period,
            COUNT(*)::DOUBLE AS orders,
            SUM(touch_hours) AS touch_hours,
            ANY_VALUE(labor_rate) AS labor_rate
        FROM order_enriched
        GROUP BY facility_id, period
        """
    ).fetchdf()
    baseline_mix = 0.0
    pilot_mix = 0.0
    for facility_id, group in rows.groupby("facility_id"):
        base = group.loc[group["period"] == "baseline"]
        pilot = group.loc[group["period"] == "pilot"]
        if len(base) != 1 or len(pilot) != 1:
            raise ValueError(f"{facility_id} is missing a baseline or pilot slice")
        base = base.iloc[0]
        pilot = pilot.iloc[0]
        saved = float(base.touch_hours) / float(base.orders) - float(pilot.touch_hours) / float(pilot.orders)
        rate = float(base.labor_rate)
        baseline_mix += saved * float(base.orders) * rate
        pilot_mix += saved * float(pilot.orders) * rate
    return {
        "baseline_mix": round(baseline_mix, 0),
        "pilot_mix": round(pilot_mix, 0),
    }


def sensitivity(hours_per_order: float, usd_per_order: float, implementation_cost: float) -> list[dict]:
    rows = []
    for monthly_orders in (800, 1500, 2500, 4000, 6500):
        hours = hours_per_order * monthly_orders
        usd_month = usd_per_order * monthly_orders
        payback = implementation_cost / max(usd_month, 1)
        rows.append(
            {
                "monthly_orders": monthly_orders,
                "hours_month": round(hours, 1),
                "usd_month": round(usd_month, 0),
                "usd_year": round(usd_month * 12, 0),
                "payback_months": round(payback, 1),
            }
        )
    return rows


def build_brief(payload: dict) -> list[str]:
    k = {row["period"]: row for row in payload["kpi_period"]}
    pick = next(row for row in payload["step_profile"] if row["step_id"] == "pick")
    fontana = next(
        row
        for row in payload["heterogeneity"]
        if row["cut"] == "facility" and row["slice"] == "FNT-12"
    )
    night = next(
        row for row in payload["heterogeneity"] if row["cut"] == "shift" and row["slice"] == "Night"
    )
    heavy = next(
        row for row in payload["heterogeneity"] if row["cut"] == "line_band" and row["slice"] == "7+ lines"
    )
    cells = {(row["cell"], row["period"]): row for row in payload["sla_cells"]}
    p = payload["tests"]
    p_value = payload["tests"]["mannwhitney"]["p_value"]
    p_text = "one-sided p < 0.001" if p_value < 0.001 else f"one-sided p = {p_value:.3f}"
    money = payload["money"]
    return [
        (
            f"Dock-to-stage median moved from {k['baseline']['median_cycle']:.1f} min "
            f"to {k['pilot']['median_cycle']:.1f} min. The bootstrap 95% interval on that "
            f"drop is {p['bootstrap']['ci95_low']:.1f}–{p['bootstrap']['ci95_high']:.1f} minutes "
            f"(Mann–Whitney {p_text})."
        ),
        (
            f"Pick was the recovered bottleneck: {pick['baseline_share_pct']}% of baseline dwell, "
            f"{pick['minutes_recovered']} minutes faster on average after zone-pick. "
            f"Fontana recovered {fontana['recovered_minutes']} minutes at the median; "
            f"night shift recovered {night['recovered_minutes']}."
        ),
        (
            f"Same-day miss rate fell from {k['baseline']['sla_miss_pct']}% to "
            f"{k['pilot']['sla_miss_pct']}%. Fontana night, the worst bay, went from "
            f"{cells[('Fontana night', 'baseline')]['sla_miss_pct']}% to "
            f"{cells[('Fontana night', 'pilot')]['sla_miss_pct']}%. "
            f"Cartons with 7 or more lines missed more often than that bay "
            f"({heavy['baseline_miss_pct']}% baseline, {heavy['pilot_miss_pct']}% pilot)."
        ),
        (
            f"Touch-labor spend in the eight-week window was ${money['window_usd']:,.0f} lower "
            f"even with more pilot cartons ({k['pilot']['orders']:,} vs {k['baseline']['orders']:,}). "
            f"The same per-carton cut is ${money['volume_matched_baseline_usd']:,.0f} at baseline volume "
            f"and ${money['volume_matched_pilot_usd']:,.0f} at pilot volume. "
            f"Payback on a ${payload['implementation_cost']:,.0f} spend is "
            f"{money['payback_months_observed']:.1f} months at observed volume. "
            f"Every building was treated; a live pilot still needs a held-out control week."
        ),
    ]


def export(con: duckdb.DuckDBPyConnection | None = None) -> dict:
    own_connection = con is None
    con = con or connect()
    orders = con.execute("SELECT period, cycle_minutes, labor_rate FROM order_enriched").fetchdf()
    baseline = orders.loc[orders["period"] == "baseline", "cycle_minutes"].to_numpy()
    pilot = orders.loc[orders["period"] == "pilot", "cycle_minutes"].to_numpy()

    sla_minutes = _assumption(con, "sla_minutes")
    implementation_cost = _assumption(con, "pilot_implementation_cost")
    if sla_minutes == int(sla_minutes):
        sla_minutes = int(sla_minutes)
    if implementation_cost == int(implementation_cost):
        implementation_cost = int(implementation_cost)
    econ = touch_unit_economics(con)
    matched = volume_matched_touch_usd(con)
    blended = float(orders["labor_rate"].mean())
    window_usd = float(
        con.execute("SELECT SUM(usd_recovered_in_window) FROM labor_bridge").fetchone()[0]
    )
    hours_recovered = float(
        con.execute(
            """
            SELECT
                SUM(touch_hours) FILTER (WHERE period = 'baseline')
                - SUM(touch_hours) FILTER (WHERE period = 'pilot')
            FROM order_enriched
            """
        ).fetchone()[0]
    )
    monthly_usd = econ["usd_per_order"] * econ["monthly_orders_observed"]

    bins = np.linspace(30, 280, 36)
    payload = {
        "sla_minutes": sla_minutes,
        "implementation_cost": implementation_cost,
        "kpi_period": _records(con, "kpi_period"),
        "step_profile": _records(con, "step_profile"),
        "step_by_shift": _records(con, "step_by_shift"),
        "step_by_cell": _records(con, "step_by_cell"),
        "facility_shift": _records(con, "facility_shift"),
        "heterogeneity": _records(con, "heterogeneity"),
        "weekly_network": _records(con, "weekly_network"),
        "weekly_trend": _records(con, "weekly_trend"),
        "weekly_shift": _records(con, "weekly_shift"),
        "weekly_cell": _records(con, "weekly_cell"),
        "worst_cartons": _records(con, "worst_cartons"),
        "exception_mix": _records(con, "exception_mix"),
        "labor_bridge": _records(con, "labor_bridge"),
        "sla_cells": _records(con, "sla_cells"),
        "step_by_facility": _records(con, "step_by_facility"),
        "orders": json.loads(
            con.execute(
                """
                SELECT
                    order_id AS id,
                    facility_id AS dc,
                    period,
                    shift,
                    channel AS ch,
                    line_count AS lines,
                    cycle_minutes AS mins,
                    sla_miss_flag AS miss,
                    rework_flag AS rw,
                    error_count AS err
                FROM order_enriched
                ORDER BY order_id
                """
            )
            .fetchdf()
            .to_json(orient="records")
        ),
        "density": {
            "baseline": density(baseline, bins),
            "pilot": density(pilot, bins),
        },
        "tests": {
            "mannwhitney": mannwhitney(baseline, pilot),
            "bootstrap": bootstrap_median_delta(baseline, pilot),
        },
        "money": {
            "blended_labor_rate": round(blended, 2),
            "window_usd": round(window_usd, 0),
            "hours_recovered_window": round(hours_recovered, 1),
            "volume_matched_baseline_usd": matched["baseline_mix"],
            "volume_matched_pilot_usd": matched["pilot_mix"],
            "payback_months_observed": round(implementation_cost / max(monthly_usd, 1), 1),
        },
        "sensitivity": sensitivity(econ["hours_per_order"], econ["usd_per_order"], implementation_cost),
        "facilities": json.loads(
            con.execute("SELECT * FROM dim_facility").fetchdf().to_json(orient="records")
        ),
    }
    payload["brief"] = build_brief(payload)

    DASHBOARD.mkdir(parents=True, exist_ok=True)
    out = DASHBOARD / "metrics.json"
    out.write_text(json.dumps(payload, indent=2))
    if own_connection:
        con.close()
    return payload


def main() -> None:
    payload = export()
    kpi = {row["period"]: row for row in payload["kpi_period"]}
    print(
        f"Baseline median {kpi['baseline']['median_cycle']} → "
        f"pilot {kpi['pilot']['median_cycle']} "
        f"(p={payload['tests']['mannwhitney']['p_value']:.2e})"
    )
    print(f"Wrote {DASHBOARD / 'metrics.json'}")


if __name__ == "__main__":
    main()
