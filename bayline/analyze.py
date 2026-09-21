"""Run the Bayline SQL marts, statistical tests, and dashboard export."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from bayline.paths import DASHBOARD, DATA, SQL

RNG = np.random.default_rng(42)
SLA_MINUTES = 120
IMPLEMENTATION_COST = 72000
WORKING_DAYS_MONTH = 26


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


def _records(con: duckdb.DuckDBPyConnection, table: str) -> list[dict]:
    frame = con.execute(f"SELECT * FROM {table}").fetchdf()
    return json.loads(frame.to_json(orient="records", date_format="iso"))


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
    deltas = np.empty(draws)
    for i in range(draws):
        b = RNG.choice(baseline, size=len(baseline), replace=True)
        p = RNG.choice(pilot, size=len(pilot), replace=True)
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


def sensitivity(baseline_hours_per_order: float, pilot_hours_per_order: float, blended_rate: float) -> list[dict]:
    rows = []
    for monthly_orders in (800, 1500, 2500, 4000, 6500):
        hours = (baseline_hours_per_order - pilot_hours_per_order) * monthly_orders
        annual = hours * 12 * blended_rate
        payback = IMPLEMENTATION_COST / max(hours * blended_rate, 1)
        rows.append(
            {
                "monthly_orders": monthly_orders,
                "hours_month": round(hours, 1),
                "usd_month": round(hours * blended_rate, 0),
                "usd_year": round(annual, 0),
                "payback_months": round(payback, 1),
            }
        )
    return rows


def board_orders(con: duckdb.DuckDBPyConnection) -> list[dict]:
    frame = con.execute(
        """
        SELECT
            order_id,
            facility_id,
            period,
            shift,
            channel,
            line_count,
            cycle_minutes,
            sla_miss_flag,
            rework_flag,
            error_count
        FROM order_enriched
        WHERE period = 'pilot'
        ORDER BY sla_miss_flag DESC, cycle_minutes DESC
        LIMIT 18
        """
    ).fetchdf()
    return json.loads(frame.to_json(orient="records"))


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
    p = payload["tests"]
    p_value = payload["tests"]["mannwhitney"]["p_value"]
    p_text = "p < 0.001" if p_value < 0.001 else f"p = {p_value:.3f}"
    return [
        (
            f"Dock-to-stage median moved from {k['baseline']['median_cycle']:.0f} min "
            f"to {k['pilot']['median_cycle']:.0f} min. The bootstrap 95% interval on that "
            f"drop is {p['bootstrap']['ci95_low']:.0f}–{p['bootstrap']['ci95_high']:.0f} minutes "
            f"(Mann–Whitney {p_text})."
        ),
        (
            f"Pick was the recovered bottleneck: {pick['baseline_share_pct']}% of baseline dwell, "
            f"{pick['minutes_recovered']} minutes faster after zone-pick. "
            f"Fontana recovered {fontana['recovered_minutes']} minutes at the median; "
            f"night shift recovered {night['recovered_minutes']}."
        ),
        (
            f"Same-day miss rate fell from {k['baseline']['sla_miss_pct']}% to "
            f"{k['pilot']['sla_miss_pct']}%. That is an operations result, not a model score: "
            f"cartons either hit the 120-minute dock or they do not."
        ),
        (
            f"At the observed mix, the eight-week window returns "
            f"${payload['money']['window_usd']:,.0f} in loaded labor. "
            f"Payback against a ${IMPLEMENTATION_COST:,.0f} slotting/training spend is "
            f"{payload['money']['payback_months_observed']:.1f} months at this volume. "
            f"The case is illustrative; a live pilot still needs a held-out control week."
        ),
    ]


def export(con: duckdb.DuckDBPyConnection | None = None) -> dict:
    own_connection = con is None
    con = con or connect()
    orders = con.execute("SELECT period, cycle_minutes, labor_rate FROM order_enriched").fetchdf()
    baseline = orders.loc[orders["period"] == "baseline", "cycle_minutes"].to_numpy()
    pilot = orders.loc[orders["period"] == "pilot", "cycle_minutes"].to_numpy()

    kpi = con.execute("SELECT * FROM kpi_period").fetchdf()
    kpi_map = {row.period: row for row in kpi.itertuples(index=False)}
    hours_base = float(kpi_map["baseline"].labor_hours)
    hours_pilot = float(kpi_map["pilot"].labor_hours)
    n_base = float(kpi_map["baseline"].orders)
    n_pilot = float(kpi_map["pilot"].orders)
    hours_per_order_base = hours_base / n_base
    hours_per_order_pilot = hours_pilot / n_pilot
    blended = float(orders["labor_rate"].mean())
    window_usd = float(
        con.execute("SELECT SUM(usd_recovered_in_window) FROM labor_bridge").fetchone()[0]
    )
    monthly_at_observed = (hours_per_order_base - hours_per_order_pilot) * ((n_base + n_pilot) / 16) * (26 / 6)
    # 8 weeks each, 6 operating days/week → observed weekly volume; scale to 26-day month.

    bins = np.linspace(30, 280, 36)
    payload = {
        "sla_minutes": SLA_MINUTES,
        "implementation_cost": IMPLEMENTATION_COST,
        "kpi_period": _records(con, "kpi_period"),
        "step_profile": _records(con, "step_profile"),
        "facility_shift": _records(con, "facility_shift"),
        "heterogeneity": _records(con, "heterogeneity"),
        "weekly_network": _records(con, "weekly_network"),
        "weekly_trend": _records(con, "weekly_trend"),
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
                """
            )
            .fetchdf()
            .to_json(orient="records")
        ),
        "board": board_orders(con),
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
            "hours_recovered_window": round(hours_base - hours_pilot, 1),
            "payback_months_observed": round(IMPLEMENTATION_COST / max(monthly_at_observed * blended, 1), 1),
        },
        "sensitivity": sensitivity(hours_per_order_base, hours_per_order_pilot, blended),
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
