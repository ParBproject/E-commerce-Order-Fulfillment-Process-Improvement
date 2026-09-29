"""Rebuild CSVs and dashboard metrics from a frozen seed."""

from bayline.analyze import export
from bayline.generate import write_tables


def main() -> None:
    write_tables()
    payload = export()
    kpi = {row["period"]: row for row in payload["kpi_period"]}
    base, pilot = kpi["baseline"], kpi["pilot"]
    money = payload["money"]
    ci = payload["tests"]["bootstrap"]
    print(
        f"Cartons {base['orders']} → {pilot['orders']}; "
        f"median {base['median_cycle']} → {pilot['median_cycle']} min; "
        f"miss {base['sla_miss_pct']}% → {pilot['sla_miss_pct']}%"
    )
    print(
        f"Touch labor in-window ${money['window_usd']:,.0f}; "
        f"payback {money['payback_months_observed']} months; "
        f"bootstrap 95% CI {ci['ci95_low']}–{ci['ci95_high']} min"
    )


if __name__ == "__main__":
    main()
