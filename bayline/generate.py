"""Simulate a three-DC fulfillment network across a baseline and a pilot.

The generating process is intentional, not decorative:

* Fontana night shift pays a travel penalty because the pick face is sprawling.
* Multi-line orders dominate pick dwell.
* Baseline QC inspects every carton; the pilot skip-lanes low-risk work.
* Newark is congested; Austin is the control site.

Seed 42 keeps the case study reproducible.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from bayline.paths import DATA

RNG = np.random.default_rng(42)

FACILITIES = [
    {
        "facility_id": "AUS-01",
        "name": "Austin Gateway",
        "region": "South Central",
        "metro": "Austin",
        "labor_rate": 24.5,
        "layout_penalty": 1.0,
        "night_penalty": 1.03,
        "congestion": 1.0,
    },
    {
        "facility_id": "EWR-07",
        "name": "Newark Hub",
        "region": "Northeast",
        "metro": "Newark",
        "labor_rate": 31.2,
        "layout_penalty": 1.05,
        "night_penalty": 1.06,
        "congestion": 1.10,
    },
    {
        "facility_id": "FNT-12",
        "name": "Fontana West",
        "region": "West",
        "metro": "Inland Empire",
        "labor_rate": 28.4,
        "layout_penalty": 1.16,
        "night_penalty": 1.20,
        "congestion": 1.04,
    },
]

STEPS = [
    ("wave_release", "Wave release", 1, 5.0, 1.5),
    ("slot_locate", "Slot locate", 2, 7.4, 2.2),
    ("pick", "Pick", 3, 31.0, 9.5),
    ("pack", "Pack", 4, 12.8, 3.6),
    ("qc", "QC gate", 5, 14.2, 4.0),
    ("stage_ship", "Stage & ship", 6, 8.4, 2.4),
]

CHANNELS = np.array(["DTC web", "Marketplace", "Store replen"])
CHANNEL_P = np.array([0.58, 0.27, 0.15])
SHIFTS = [
    ("Days", 6),
    ("Swing", 14),
    ("Night", 22),
]
SHIFT_P = np.array([0.42, 0.33, 0.25])

EXCEPTION_TYPES = [
    ("short_pick", "Short pick / slot empty"),
    ("damaged_carton", "Damaged carton"),
    ("label_mismatch", "Label mismatch"),
    ("weight_fail", "In-line weight fail"),
    ("missed_sla", "Missed same-day dock"),
]


def _clip(value: float, lo: float, hi: float) -> float:
    return float(np.clip(value, lo, hi))


def _lognormal(mean: float, sigma: float) -> float:
    draw = RNG.lognormal(mean=np.log(max(mean, 0.8)), sigma=sigma / max(mean, 0.8))
    return _clip(draw, 1.2, mean * 3.8)


def _weekdays(start: datetime, weeks: int) -> list[datetime]:
    days = []
    cursor = start
    end = start + timedelta(weeks=weeks)
    while cursor < end:
        if cursor.weekday() < 6:  # Mon-Sat network
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _line_count() -> int:
    # Heavy left tail: most cartons are 1-3 lines, a few are wave-killers.
    raw = int(RNG.negative_binomial(2, 0.42)) + 1
    return int(np.clip(raw, 1, 14))


def _order_volume(facility_id: str, shift: str, weekday: int) -> int:
    base = 5.4
    if facility_id == "EWR-07":
        base += 0.8
    if facility_id == "FNT-12":
        base += 0.4
    if shift == "Night":
        base -= 1.1
    if weekday == 5:
        base -= 1.4
    return int(max(2, RNG.poisson(base)))


def _pilot_effects(step_id: str, *, facility_id: str, shift: str, lines: int, low_risk: bool) -> float:
    """Return a multiplicative dwell factor for the redesigned flow."""
    factor = 1.0
    if step_id == "pick":
        factor *= 0.62 if facility_id == "FNT-12" else 0.76
        if shift == "Night" and facility_id == "FNT-12":
            factor *= 0.92  # zone pick cuts travel; night still slower
        if lines >= 6:
            factor *= 0.93
    elif step_id == "qc":
        factor *= 0.34 if low_risk else 0.82
    elif step_id == "slot_locate":
        factor *= 0.78
    elif step_id == "pack":
        factor *= 0.88
    elif step_id == "wave_release":
        factor *= 0.92
    elif step_id == "stage_ship":
        factor *= 0.90
    return factor


def _step_mean(
    step_id: str,
    base_mean: float,
    facility: dict,
    shift: str,
    lines: int,
    channel: str,
    pilot: bool,
    low_risk: bool,
) -> float:
    mean = base_mean * facility["layout_penalty"] * facility["congestion"]
    if shift == "Night":
        mean *= facility["night_penalty"]
    if step_id == "pick":
        mean *= 0.72 + 0.18 * lines
        if channel == "Store replen":
            mean *= 1.12
    if step_id == "qc" and channel == "Marketplace":
        mean *= 1.08
    if step_id == "slot_locate" and lines >= 5:
        mean *= 1.16
    if pilot:
        mean *= _pilot_effects(
            step_id,
            facility_id=facility["facility_id"],
            shift=shift,
            lines=lines,
            low_risk=low_risk,
        )
    return mean


def _maybe_exception(pilot: bool, step_id: str, lines: int, facility_id: str) -> tuple[str, str] | None:
    p = 0.045
    if facility_id == "FNT-12":
        p += 0.02
    if lines >= 6:
        p += 0.015
    if pilot:
        p *= 0.62
    if step_id not in {"pick", "qc", "pack"}:
        p *= 0.35
    if RNG.random() > p:
        return None
    if step_id == "pick":
        return EXCEPTION_TYPES[0]
    if step_id == "pack":
        return EXCEPTION_TYPES[1]
    if RNG.random() < 0.5:
        return EXCEPTION_TYPES[2]
    return EXCEPTION_TYPES[3]


def simulate() -> dict[str, pd.DataFrame]:
    baseline_start = datetime(2025, 1, 6)
    pilot_start = datetime(2025, 3, 10)
    periods = [
        ("baseline", baseline_start, 8, False),
        ("pilot", pilot_start, 8, True),
    ]

    orders = []
    steps = []
    exceptions = []
    seq = 10000

    for period_name, start, weeks, pilot in periods:
        for day in _weekdays(start, weeks):
            for facility in FACILITIES:
                for shift_name, hour in SHIFTS:
                    n = _order_volume(facility["facility_id"], shift_name, day.weekday())
                    for _ in range(n):
                        minute = int(RNG.integers(8, 52))
                        dropped_at = day.replace(hour=hour % 24, minute=minute, second=int(RNG.integers(0, 50)))
                        seq += 1
                        order_id = f"BL-{seq}"
                        lines = _line_count()
                        channel = str(RNG.choice(CHANNELS, p=CHANNEL_P))
                        low_risk = lines <= 2 and channel != "Store replen" and RNG.random() < 0.78
                        hazmat = bool(RNG.random() < 0.04)
                        if hazmat:
                            low_risk = False
                        promised = dropped_at + timedelta(minutes=120)

                        cursor = dropped_at
                        cycle = 0.0
                        error_count = 0
                        rework = 0
                        for step_id, step_name, step_seq, base_mean, sigma in STEPS:
                            mean = _step_mean(
                                step_id,
                                base_mean,
                                facility,
                                shift_name,
                                lines,
                                channel,
                                pilot,
                                low_risk,
                            )
                            dwell = round(_lognormal(mean, sigma), 1)
                            started = cursor
                            ended = started + timedelta(minutes=dwell)
                            steps.append(
                                {
                                    "order_id": order_id,
                                    "step_id": step_id,
                                    "step_name": step_name,
                                    "step_seq": step_seq,
                                    "started_at": started.isoformat(timespec="seconds"),
                                    "ended_at": ended.isoformat(timespec="seconds"),
                                    "dwell_minutes": dwell,
                                }
                            )
                            cycle += dwell
                            cursor = ended
                            exc = _maybe_exception(pilot, step_id, lines, facility["facility_id"])
                            if exc:
                                code, label = exc
                                extra = round(_clip(RNG.normal(11, 4), 4, 28), 1)
                                exceptions.append(
                                    {
                                        "order_id": order_id,
                                        "step_id": step_id,
                                        "exception_code": code,
                                        "exception_label": label,
                                        "minutes_added": extra,
                                        "rework_flag": int(code in {"short_pick", "label_mismatch", "weight_fail"}),
                                    }
                                )
                                error_count += 1
                                if code in {"short_pick", "label_mismatch", "weight_fail"}:
                                    rework = 1
                                cycle += extra
                                cursor += timedelta(minutes=extra)

                        sla_miss = int(cycle > 120)
                        if sla_miss:
                            exceptions.append(
                                {
                                    "order_id": order_id,
                                    "step_id": "stage_ship",
                                    "exception_code": "missed_sla",
                                    "exception_label": "Missed same-day dock",
                                    "minutes_added": round(cycle - 120, 1),
                                    "rework_flag": 0,
                                }
                            )

                        orders.append(
                            {
                                "order_id": order_id,
                                "facility_id": facility["facility_id"],
                                "period": period_name,
                                "pilot_flag": int(pilot),
                                "dropped_at": dropped_at.isoformat(timespec="seconds"),
                                "promised_at": promised.isoformat(timespec="seconds"),
                                "shift": shift_name,
                                "channel": channel,
                                "line_count": lines,
                                "low_risk_flag": int(low_risk),
                                "hazmat_flag": int(hazmat),
                                "cycle_minutes": round(cycle, 1),
                                "error_count": error_count,
                                "rework_flag": rework,
                                "sla_miss_flag": sla_miss,
                            }
                        )

    facility_df = pd.DataFrame(FACILITIES)
    step_dim = pd.DataFrame(
        [
            {"step_id": s[0], "step_name": s[1], "step_seq": s[2], "baseline_mean_minutes": s[3]}
            for s in STEPS
        ]
    )
    labor = pd.DataFrame(
        [
            {
                "assumption_id": "hourly_loaded_labor",
                "description": "Loaded warehouse labor including fringe",
                "unit": "USD_per_hour",
            },
            {
                "assumption_id": "sla_minutes",
                "description": "Dock-to-stage same-day target",
                "unit": "minutes",
                "value": 120,
            },
            {
                "assumption_id": "pilot_implementation_cost",
                "description": "Zone-pick slotting, rack relabel, skip-lane training",
                "unit": "USD",
                "value": 72000,
            },
            {
                "assumption_id": "working_days_month",
                "description": "Network operating days used in capacity math",
                "unit": "days",
                "value": 26,
            },
        ]
    )
    # Labor rates already live on the facility dimension; keep a tidy assumptions file.
    labor.loc[labor["assumption_id"] == "hourly_loaded_labor", "value"] = np.nan

    return {
        "dim_facility": facility_df,
        "dim_step": step_dim,
        "dim_assumption": labor,
        "fact_orders": pd.DataFrame(orders),
        "fact_order_steps": pd.DataFrame(steps),
        "fact_exceptions": pd.DataFrame(exceptions),
    }


def write_tables(tables: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    DATA.mkdir(parents=True, exist_ok=True)
    tables = tables or simulate()
    for name, frame in tables.items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False)
    return tables


def main() -> None:
    tables = write_tables()
    orders = tables["fact_orders"]
    print(f"Wrote {len(orders)} orders to {DATA}")
    print(orders.groupby("period")["cycle_minutes"].median())


if __name__ == "__main__":
    main()
