"""Command-line generation of the four validation-evidence artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import build_validation_evidence, write_validation_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    root = arguments.repository_root.resolve()
    output = arguments.output.resolve()
    if output.is_relative_to(root):
        parser.error("--output must be outside the repository tree")
    evidence = build_validation_evidence(root)
    artifacts = write_validation_report(evidence, output)
    print(
        json.dumps(
            {
                name: {"path": str(item.path), "sha256": item.sha256}
                for name, item in (
                    ("html", artifacts.html),
                    ("json", artifacts.json),
                    ("comparisons_csv", artifacts.comparisons_csv),
                    ("case_ledger_csv", artifacts.case_ledger_csv),
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
