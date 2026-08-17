"""Regenerate and classify differences from the committed baseline."""

import argparse
import sys
import tempfile
import time
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from tests.golden_master.cases import build_cases  # noqa: E402
from tests.golden_master.core import (  # noqa: E402
    compare_rows,
    generate_rows,
    load_csv,
    rows_to_csv,
)

CANONICAL = Path(__file__).with_name("baseline.csv")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=CANONICAL)
    parser.add_argument("--strict-path", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pvt-golden-") as directory:
        current = Path(directory) / "current.csv"
        current.write_text(
            rows_to_csv(generate_rows(build_cases(), REPOSITORY)),
            encoding="utf-8",
            newline="",
        )
        differences = compare_rows(load_csv(args.baseline), load_csv(current))
    for classification, items in differences.items():
        print(f"{classification}: {len(items)}")
        for item in items:
            print(f"  {item}")
    print(f"comparison runtime: {time.perf_counter() - started:.3f}s")
    physical = (
        differences["PHYSICAL_RESULT_DRIFT"]
        or differences["MISSING_CASE"]
        or differences["EXTRA_CASE"]
    )
    if physical or (args.strict_path and differences["NUMERICAL_PATH_CHANGE"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
