"""Command-line generator for the canonical golden master."""

import argparse
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from tests.golden_master.cases import build_cases  # noqa: E402
from tests.golden_master.core import generate_rows, rows_to_csv  # noqa: E402

CANONICAL = Path(__file__).with_name("baseline.csv")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace-canonical", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == CANONICAL.resolve() and not args.replace_canonical:
        parser.error(
            "refusing to overwrite canonical baseline without --replace-canonical"
        )
    rows = generate_rows(build_cases(), REPOSITORY)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rows_to_csv(rows), encoding="utf-8", newline="")
    print(f"wrote {len(rows)} cases to {output}")


if __name__ == "__main__":
    main()
