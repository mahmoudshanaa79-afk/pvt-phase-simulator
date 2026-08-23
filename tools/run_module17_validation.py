"""Regenerate the deterministic Module 17 experimental-validation artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from pvt_phase_simulator.experimental_validation import (
    load_experimental_vle_dataset,
    summarize_283_38_k_sensitivity,
    summarize_validation_results,
    validate_experimental_dataset,
    validation_results_to_csv,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> None:
    """Load the immutable source data and write derived results only."""

    root = _arguments().root.resolve()
    dataset = load_experimental_vle_dataset(
        root / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv",
        root / "data/experimental/may_2015_source_manifest.json",
    )
    results = validate_experimental_dataset(dataset)
    summaries = summarize_validation_results(results)
    output_directory = root / "docs/validation"
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "module17_vle_validation.csv").write_text(
        validation_results_to_csv(results), encoding="utf-8", newline=""
    )
    summary_document = {
        "source_id": dataset.source.source_id,
        "normalized_csv_sha256": dataset.source.normalized_csv_sha256,
        "source_point_count": len(dataset.points),
        "interpretation": {
            "production_selected_metrics": (
                "Prospective outputs of the unchanged production solver."
            ),
            "dew_branch_diagnostics": (
                "Retrospective validation-only scan; the experimental pressure "
                "identifies the nearest already-existing PR root but never replaces "
                "the production prediction."
            ),
        },
        "source_anomaly_sensitivity_283_38_k": {
            direction: asdict(summary)
            for direction, summary in summarize_283_38_k_sensitivity(results).items()
        },
        "systems": [asdict(summary) for summary in summaries],
    }
    (output_directory / "module17_vle_validation_summary.json").write_text(
        json.dumps(summary_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(f"validated {len(results)} source states")
    print(json.dumps(summary_document, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
