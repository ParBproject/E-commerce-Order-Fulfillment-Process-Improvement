"""Build the DuckDB analytical model and export employer-review tables."""

from __future__ import annotations

from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "sql" / "analytics_model.sql"
OUTPUT_DIR = ROOT / "outputs"


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    connection = duckdb.connect(database=":memory:")
    connection.execute(f"SET home_directory='{ROOT.as_posix()}'")

    # DuckDB read_csv_auto resolves relative paths from the current process.
    # Change into the repository directory through explicit absolute view inputs
    # by executing the SQL with the process launched from the repo root.
    connection.execute(SQL_PATH.read_text(encoding="utf-8"))

    exports = {
        "state_kpis": "state_kpis.csv",
        "kpi_improvement": "kpi_improvement.csv",
        "process_step_summary": "process_step_summary.csv",
        "bottleneck_pareto": "bottleneck_pareto.csv",
        "daily_operations": "daily_operations.csv",
        "order_exceptions": "order_exceptions.csv",
        "data_quality_report": "data_quality_report.csv",
    }

    for view, filename in exports.items():
        frame = connection.execute(f"SELECT * FROM {view}").fetchdf()
        frame.to_csv(OUTPUT_DIR / filename, index=False)
        print(f"{view}: {len(frame):,} rows -> outputs/{filename}")


if __name__ == "__main__":
    main()
