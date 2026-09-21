"""Rebuild CSVs and dashboard metrics from a frozen seed."""

from bayline.analyze import export
from bayline.generate import write_tables


def main() -> None:
    write_tables()
    export()


if __name__ == "__main__":
    main()
