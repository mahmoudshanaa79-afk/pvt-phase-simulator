"""Run and print the extended deterministic Module 14 verification report."""

from time import perf_counter

from tests.derivative_verification import run_verification_matrix


def main() -> None:
    """Execute the full matrix and print stable scientific error metrics."""

    started = perf_counter()
    report = run_verification_matrix()
    families = sorted({entry.family for entry in report.entries})
    print(f"EXPLICIT_CASE_SPECIFICATIONS {len(report.explicit_case_ids)}")
    print(f"SCALAR_COMPARISONS {len(report.entries)}")
    for family in families:
        summary = report.summary(family)
        print(
            "FAMILY "
            f"{family} count={summary.count} "
            f"max_abs={summary.maximum_absolute_error:.17g} "
            f"max_rel={summary.maximum_relative_error:.17g} "
            f"median_abs={summary.median_absolute_error:.17g} "
            f"worst={summary.worst_case_id}"
        )
    print(f"EXCLUDED {len(report.exclusions)}")
    for case_id, reason in report.exclusions:
        print(f"EXCLUSION {case_id} reason={reason}")
    for row in report.near_singular:
        print(
            "NEAR_SINGULAR "
            f"A={row.A:.17g} B={row.B:.17g} "
            f"abs_Fz={row.absolute_cubic_partial_z:.17g} "
            f"abs_derivative={row.derivative_magnitude:.17g} "
            f"abs_error={row.absolute_error:.17g}"
        )
    print(f"RUNTIME_SECONDS {perf_counter() - started:.6f}")


if __name__ == "__main__":
    main()
