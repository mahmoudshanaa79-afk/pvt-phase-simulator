"""Run the deterministic Module 15 historical/accelerated/Newton matrix."""

from dataclasses import dataclass

from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    trace_bubble_branch,
    trace_dew_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationPressureResult,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    case: str
    method: str
    status: str
    pressure_pa: float | None
    incipient_composition: tuple[float, ...]
    residual: float | None
    historical_inner_iterations: int
    historical_function_calls: int
    eos_calls: int
    fugacity_calls: int
    newton_iterations: int
    full_steps: int
    backtracked_steps: int
    rejected_steps: int
    fallback_used: bool

    @property
    def work_units(self) -> int:
        return self.eos_calls + self.fugacity_calls


def _mixture(items: tuple[tuple[Component, float], ...]) -> FluidMixture:
    return FluidMixture(tuple(MixtureComponent(*item) for item in items))


BINARY = _mixture(((METHANE, 0.5), (ETHANE, 0.5)))
ASYMMETRIC_BINARY = _mixture(((METHANE, 0.2), (ETHANE, 0.8)))
METHANE_PROPANE = _mixture(((METHANE, 0.6), (PROPANE, 0.4)))
TERNARY = _mixture(((METHANE, 0.6), (ETHANE, 0.3), (PROPANE, 0.1)))
PURE = _mixture(((METHANE, 1.0),))


def _saturation_work(result: SaturationPressureResult) -> tuple[int, int, int]:
    historical_phase_calls = sum(
        1 + len(evaluation.history) for evaluation in result.evaluation_history
    )
    attempt = result.newton_attempt
    newton_evaluations = 0 if attempt is None else attempt.function_evaluations
    # Each Newton residual evaluates two EOS phases and then the same two
    # fixed-root fugacity derivative states. A successful full-order
    # reconstruction evaluates two additional phase states.
    newton_eos = 4 * newton_evaluations
    newton_fugacity = 4 * newton_evaluations
    if attempt is not None and attempt.converged:
        return newton_eos + 2, newton_fugacity + 2, 0
    return (
        newton_eos + historical_phase_calls,
        newton_fugacity + historical_phase_calls,
        sum(len(evaluation.history) for evaluation in result.evaluation_history),
    )


def _record(
    case: str,
    method: str,
    result: SaturationPressureResult,
) -> BenchmarkResult:
    eos_calls, fugacity_calls, historical_iterations = _saturation_work(result)
    attempt = result.newton_attempt
    return BenchmarkResult(
        case=case,
        method=method,
        status=result.status.value,
        pressure_pa=result.pressure_pa,
        incipient_composition=result.incipient_composition,
        residual=result.maximum_fugacity_equilibrium_residual,
        historical_inner_iterations=historical_iterations,
        historical_function_calls=result.pressure_solver_function_calls,
        eos_calls=eos_calls,
        fugacity_calls=fugacity_calls,
        newton_iterations=0 if attempt is None else attempt.iteration_count,
        full_steps=0 if attempt is None else attempt.full_steps,
        backtracked_steps=0 if attempt is None else attempt.backtracked_steps,
        rejected_steps=0 if attempt is None else attempt.rejected_steps,
        fallback_used=attempt is not None and not attempt.converged,
    )


def _run_saturation_case(
    case: str,
    mixture: FluidMixture,
    temperature_k: float,
    kind: SaturationKind,
) -> tuple[BenchmarkResult, ...]:
    rows: list[BenchmarkResult] = []
    for method, kwargs in (
        ("historical", {}),
        ("accelerated", {"successive_substitution_acceleration_enabled": True}),
        ("newton", {"saturation_newton_enabled": True}),
    ):
        result = calculate_saturation_pressure(
            mixture,
            temperature_k,
            kind,
            **kwargs,  # type: ignore[arg-type]
        )
        rows.append(_record(case, method, result))
    return tuple(rows)


def _run_envelope_case(
    case: str,
    mixture: FluidMixture,
    start_temperature_k: float,
    target_temperature_k: float,
    step_k: float,
    kind: SaturationKind,
) -> tuple[BenchmarkResult, ...]:
    rows: list[BenchmarkResult] = []
    trace = (
        trace_bubble_branch if kind is SaturationKind.BUBBLE_POINT else trace_dew_branch
    )
    for method, settings_kwargs in (
        ("historical", {}),
        ("accelerated", {"successive_substitution_acceleration_enabled": True}),
        ("newton", {"saturation_newton_enabled": True}),
    ):
        settings = EnvelopeContinuationSettings(
            target_temperature_k=target_temperature_k,
            initial_temperature_step_k=step_k,
            maximum_points=8,
            **settings_kwargs,  # type: ignore[arg-type]
        )
        branch = trace(mixture, settings, start_temperature_k)
        if branch.points:
            endpoint = branch.points[-1].saturation_result
            row = _record(case, method, endpoint)
            accepted = tuple(point.saturation_result for point in branch.points)
            eos_calls = sum(_saturation_work(item)[0] for item in accepted)
            fugacity_calls = sum(_saturation_work(item)[1] for item in accepted)
            historical_iterations = sum(_saturation_work(item)[2] for item in accepted)
            newton_iterations = sum(
                0
                if item.newton_attempt is None
                else item.newton_attempt.iteration_count
                for item in accepted
            )
            full_steps = sum(
                0 if item.newton_attempt is None else item.newton_attempt.full_steps
                for item in accepted
            )
            backtracked = sum(
                0
                if item.newton_attempt is None
                else item.newton_attempt.backtracked_steps
                for item in accepted
            )
            rejected = sum(
                0 if item.newton_attempt is None else item.newton_attempt.rejected_steps
                for item in accepted
            )
            fallback = any(
                item.newton_attempt is not None and not item.newton_attempt.converged
                for item in accepted
            )
            rows.append(
                BenchmarkResult(
                    case,
                    method,
                    branch.termination_reason.value,
                    row.pressure_pa,
                    row.incipient_composition,
                    row.residual,
                    historical_iterations,
                    sum(item.pressure_solver_function_calls for item in accepted),
                    eos_calls,
                    fugacity_calls,
                    newton_iterations,
                    full_steps,
                    backtracked,
                    rejected,
                    fallback,
                )
            )
        else:
            rows.append(
                BenchmarkResult(
                    case,
                    method,
                    branch.termination_reason.value,
                    None,
                    (),
                    None,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    False,
                )
            )
    return tuple(rows)


def run_benchmarks() -> tuple[BenchmarkResult, ...]:
    rows: list[BenchmarkResult] = []
    saturation_cases = (
        ("easy binary bubble", BINARY, 220.0, SaturationKind.BUBBLE_POINT),
        (
            "known adverse binary bubble",
            ASYMMETRIC_BINARY,
            220.0,
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "difficult binary bubble",
            METHANE_PROPANE,
            250.0,
            SaturationKind.BUBBLE_POINT,
        ),
        ("easy binary dew", BINARY, 220.0, SaturationKind.DEW_POINT),
        (
            "difficult binary dew",
            ASYMMETRIC_BINARY,
            180.0,
            SaturationKind.DEW_POINT,
        ),
        (
            "CH4/C3 60/40 dew 250 K",
            METHANE_PROPANE,
            250.0,
            SaturationKind.DEW_POINT,
        ),
        ("ternary bubble", TERNARY, 220.0, SaturationKind.BUBBLE_POINT),
        ("ternary dew", TERNARY, 220.0, SaturationKind.DEW_POINT),
        ("pure methane", PURE, 170.0, SaturationKind.BUBBLE_POINT),
        (
            "near-critical applicable",
            PURE,
            185.0,
            SaturationKind.BUBBLE_POINT,
        ),
    )
    for case in saturation_cases:
        rows.extend(_run_saturation_case(*case))
    rows.extend(
        _run_envelope_case(
            "continuation-only bubble",
            BINARY,
            240.0,
            250.0,
            5.0,
            SaturationKind.BUBBLE_POINT,
        )
    )
    rows.extend(
        _run_envelope_case(
            "short bubble envelope",
            BINARY,
            200.0,
            210.0,
            5.0,
            SaturationKind.BUBBLE_POINT,
        )
    )
    rows.extend(
        _run_envelope_case(
            "short dew envelope",
            BINARY,
            200.0,
            210.0,
            5.0,
            SaturationKind.DEW_POINT,
        )
    )
    return tuple(rows)


def _format_float(value: float | None) -> str:
    return "-" if value is None else f"{value:.12g}"


def _format_composition(values: tuple[float, ...]) -> str:
    return "-" if not values else ",".join(f"{value:.10g}" for value in values)


def main() -> None:
    rows = run_benchmarks()
    print(
        "| Case | Method | Status | Pressure (Pa) | Incipient composition | "
        "Residual | Hist. inner | Hist. calls | EOS calls | Fugacity calls | "
        "Newton it. | Full | Backtracked | Rejected | Fallback |"
    )
    print(
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: | --- |"
    )
    for row in rows:
        print(
            f"| {row.case} | {row.method} | {row.status} | "
            f"{_format_float(row.pressure_pa)} | "
            f"{_format_composition(row.incipient_composition)} | "
            f"{_format_float(row.residual)} | "
            f"{row.historical_inner_iterations} | {row.historical_function_calls} | "
            f"{row.eos_calls} | {row.fugacity_calls} | {row.newton_iterations} | "
            f"{row.full_steps} | {row.backtracked_steps} | {row.rejected_steps} | "
            f"{'yes' if row.fallback_used else 'no'} |"
        )
    grouped = {
        case: {row.method: row for row in rows if row.case == case}
        for case in dict.fromkeys(row.case for row in rows)
    }
    improved = tied = worsened = fallback = 0
    improved_reductions: list[float] = []
    all_case_reductions: list[float] = []
    for methods in grouped.values():
        historical = methods["historical"].work_units
        newton = methods["newton"].work_units
        fallback += int(methods["newton"].fallback_used)
        if historical:
            all_case_reductions.append(1.0 - newton / historical)
        if newton < historical:
            improved += 1
            if historical:
                improved_reductions.append(1.0 - newton / historical)
        elif newton == historical:
            tied += 1
        else:
            worsened += 1
    mean_improved_reduction = (
        sum(improved_reductions) / len(improved_reductions)
        if improved_reductions
        else 0.0
    )
    mean_all_reduction = (
        sum(all_case_reductions) / len(all_case_reductions)
        if all_case_reductions
        else 0.0
    )
    print(
        f"SUMMARY improved={improved} tied={tied} worsened={worsened} "
        f"fallback={fallback} "
        f"mean_improved_work_reduction={mean_improved_reduction:.6f} "
        f"mean_all_work_reduction={mean_all_reduction:.6f}"
    )
    print(
        "WORK_METRIC benchmark-defined EOS calls + fugacity calls; "
        "not wall-clock runtime or a universal speedup"
    )
    regression = next(
        row
        for row in rows
        if row.case == "CH4/C3 60/40 dew 250 K" and row.method == "newton"
    )
    print(
        "CH4_C3_NEWTON "
        f"pressure={regression.pressure_pa!r} "
        f"composition={regression.incipient_composition!r}"
    )
    pure = next(
        row for row in rows if row.case == "pure methane" and row.method == "newton"
    )
    print(f"PURE_NEWTON pressure={pure.pressure_pa!r}")


if __name__ == "__main__":
    main()
