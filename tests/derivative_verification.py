"""Deterministic Module 14 verification matrix and error reporting."""

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from statistics import median

from pvt_phase_simulator.eos.derivatives import (
    calculate_fixed_root_compressibility_derivative,
    calculate_fixed_root_mixture_fugacity_derivatives,
    calculate_mixture_parameter_derivatives,
    calculate_pure_component_temperature_derivatives,
    calculate_pure_dimensionless_parameter_derivatives,
)
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_a_parameter,
    calculate_alpha,
    calculate_compressibility_roots,
)
from pvt_phase_simulator.fluid_models import ETHANE, METHANE, PROPANE, Component
from tests.derivative_reference import (
    RootTrackingError,
    VerificationState,
    complex_step_composition,
    complex_step_pressure,
    complex_step_temperature,
    composition_richardson,
    independent_cubic_partials,
    log_pressure_richardson,
    ordinary_state,
    pressure_richardson,
    richardson_vector,
    temperature_richardson,
)

COMPLEX_STEP = 1e-30


@dataclass(frozen=True, slots=True)
class VerificationEntry:
    """One analytical/reference scalar comparison."""

    family: str
    case_id: str
    route: str
    analytical: float
    reference: float
    absolute_error: float
    relative_error: float | None


@dataclass(frozen=True, slots=True)
class FamilySummary:
    """Aggregate deterministic error metrics for one derivative family."""

    family: str
    count: int
    maximum_absolute_error: float
    maximum_relative_error: float
    median_absolute_error: float
    worst_case_id: str


@dataclass(frozen=True, slots=True)
class NearSingularObservation:
    """Conditioning evidence while approaching a multiple cubic root."""

    A: float
    B: float
    root: float
    absolute_cubic_partial_z: float
    derivative_magnitude: float
    reference_derivative: float
    absolute_error: float


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Complete Module 14 scalar comparisons, exclusions, and study rows."""

    explicit_case_ids: tuple[str, ...]
    entries: tuple[VerificationEntry, ...]
    exclusions: tuple[tuple[str, str], ...]
    near_singular: tuple[NearSingularObservation, ...]

    def summary(self, family: str) -> FamilySummary:
        selected = tuple(entry for entry in self.entries if entry.family == family)
        if not selected:
            raise ValueError(f"no verification entries for {family}")
        worst = max(selected, key=lambda entry: entry.absolute_error)
        relative = tuple(
            entry.relative_error
            for entry in selected
            if entry.relative_error is not None
        )
        return FamilySummary(
            family=family,
            count=len(selected),
            maximum_absolute_error=worst.absolute_error,
            maximum_relative_error=max(relative, default=0.0),
            median_absolute_error=median(entry.absolute_error for entry in selected),
            worst_case_id=worst.case_id,
        )

    @property
    def exclusion_reason_counts(self) -> Counter[str]:
        return Counter(reason for _, reason in self.exclusions)


PURE_TEMPERATURE_CASES: tuple[tuple[str, Component, float], ...] = (
    ("pure_methane_subcritical", METHANE, 150.0),
    ("pure_methane_near_critical", METHANE, 0.98 * METHANE.critical_temperature_k),
    ("pure_methane_supercritical", METHANE, 350.0),
    ("pure_ethane_subcritical", ETHANE, 240.0),
    ("pure_ethane_near_critical", ETHANE, 0.98 * ETHANE.critical_temperature_k),
    ("pure_ethane_supercritical", ETHANE, 450.0),
    ("pure_propane_subcritical", PROPANE, 300.0),
    ("pure_propane_near_critical", PROPANE, 0.98 * PROPANE.critical_temperature_k),
    ("pure_propane_supercritical", PROPANE, 550.0),
)

EOS_STATES: tuple[VerificationState, ...] = (
    VerificationState("pure_methane_vapor", (METHANE,), (1.0,), 150.0, 1_000_000.0, -1),
    VerificationState(
        "pure_ethane_near_critical",
        (ETHANE,),
        (1.0,),
        0.98 * ETHANE.critical_temperature_k,
        3_000_000.0,
        -1,
    ),
    VerificationState(
        "pure_propane_supercritical", (PROPANE,), (1.0,), 550.0, 8_000_000.0, -1
    ),
    VerificationState(
        "ch4_c2_low_asymmetric",
        (METHANE, ETHANE),
        (0.8, 0.2),
        250.0,
        100_000.0,
        -1,
    ),
    VerificationState(
        "ch4_c2_high_balanced",
        (METHANE, ETHANE),
        (0.5, 0.5),
        250.0,
        8_000_000.0,
        -1,
    ),
    VerificationState(
        "ch4_c3_three_root_liquid",
        (METHANE, PROPANE),
        (0.6, 0.4),
        250.0,
        3_000_000.0,
        0,
    ),
    VerificationState(
        "ch4_c3_three_root_vapor",
        (METHANE, PROPANE),
        (0.6, 0.4),
        250.0,
        3_000_000.0,
        -1,
    ),
    VerificationState(
        "ternary_balanced",
        (METHANE, ETHANE, PROPANE),
        (0.4, 0.4, 0.2),
        280.0,
        3_000_000.0,
        -1,
    ),
    VerificationState(
        "ternary_asymmetric",
        (METHANE, ETHANE, PROPANE),
        (0.7, 0.2, 0.1),
        250.0,
        2_000_000.0,
        -1,
    ),
    VerificationState(
        "ternary_reversed",
        (PROPANE, ETHANE, METHANE),
        (0.2, 0.4, 0.4),
        280.0,
        3_000_000.0,
        -1,
        0,
    ),
    VerificationState(
        "ch4_c3_near_pure",
        (METHANE, PROPANE),
        (0.995, 0.005),
        280.0,
        1_000_000.0,
        -1,
    ),
    VerificationState(
        "ternary_zero_ethane",
        (METHANE, ETHANE, PROPANE),
        (0.6, 0.0, 0.4),
        250.0,
        2_000_000.0,
        -1,
    ),
)


def _entry(
    family: str,
    case_id: str,
    route: str,
    analytical: float,
    reference: float,
) -> VerificationEntry:
    absolute_error = abs(analytical - reference)
    scale = max(abs(analytical), abs(reference))
    relative_error = None if scale <= 1e-14 else absolute_error / scale
    return VerificationEntry(
        family=family,
        case_id=case_id,
        route=route,
        analytical=analytical,
        reference=reference,
        absolute_error=absolute_error,
        relative_error=relative_error,
    )


def _append_vector_entries(
    entries: list[VerificationEntry],
    family: str,
    case_id: str,
    route: str,
    analytical: tuple[float, ...],
    reference: tuple[float, ...],
    labels: tuple[str, ...],
) -> None:
    if not (len(analytical) == len(reference) == len(labels)):
        raise ValueError("verification vector dimensions disagree")
    entries.extend(
        _entry(family, f"{case_id}:{label}", route, actual, expected)
        for actual, expected, label in zip(analytical, reference, labels, strict=True)
    )


def _flatten(matrix: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    return tuple(value for row in matrix for value in row)


def _temperature_values(state_value: object) -> tuple[float, ...]:
    state = state_value
    return (
        *_flatten(state.pair_attraction_parameters),
        *state.component_attraction_sums,
        state.parameters.a_alpha_mix,
        state.parameters.b_mix,
        state.parameters.A_mix,
        state.parameters.B_mix,
    )


def _parameter_values(state_value: object) -> tuple[float, ...]:
    state = state_value
    return (state.parameters.A_mix, state.parameters.B_mix)


def _root_and_log_phi(state_value: object) -> tuple[float, ...]:
    state = state_value
    return (state.root, *state.log_fugacity_coefficients)


def _composition_values(state_value: object) -> tuple[float, ...]:
    state = state_value
    return (
        state.parameters.a_alpha_mix,
        state.parameters.b_mix,
        state.parameters.A_mix,
        state.parameters.B_mix,
        *state.component_attraction_sums,
    )


def _record_cubic_identity(
    entries: list[VerificationEntry],
    case_id: str,
    suffix: str,
    root: float,
    A: float,
    B: float,
    d_A: float,
    d_B: float,
    d_z: float,
) -> None:
    partial_z, partial_A, partial_B = independent_cubic_partials(root, A, B)
    residual = partial_A * d_A + partial_B * d_B + partial_z * d_z
    entries.append(
        _entry(
            "cubic_identity",
            f"{case_id}:{suffix}",
            "independent_algebra",
            residual,
            0.0,
        )
    )


def _pure_entries(entries: list[VerificationEntry]) -> None:
    for case_id, component, temperature in PURE_TEMPERATURE_CASES:
        analytical = calculate_pure_component_temperature_derivatives(
            component, temperature
        )
        synthetic_state = VerificationState(
            case_id, (component,), (1.0,), temperature, 1_000_000.0, -1
        )
        complex_values = complex_step_temperature(synthetic_state)
        complex_reference = (
            complex_values.alpha[0].imag / COMPLEX_STEP,
            complex_values.a_alpha[0].imag / COMPLEX_STEP,
        )
        actual = (
            analytical.alpha_temperature_derivative_per_k,
            analytical.a_alpha_temperature_derivative,
        )
        labels = ("alpha_T", "a_alpha_T")
        _append_vector_entries(
            entries,
            "pure_alpha_aalpha_temperature",
            case_id,
            "complex_step",
            actual,
            complex_reference,
            labels,
        )
        a_value = calculate_a_parameter(
            component.critical_temperature_k, component.critical_pressure_pa
        )

        def pure_values(
            delta: float,
            *,
            current_temperature: float = temperature,
            current_component: Component = component,
            current_a: float = a_value,
        ) -> tuple[float, float]:
            alpha_value = calculate_alpha(
                current_temperature + delta,
                current_component.critical_temperature_k,
                current_component.acentric_factor,
            )
            return alpha_value, current_a * alpha_value

        richardson = richardson_vector(
            pure_values,
            1e-3 * temperature,
        )
        _append_vector_entries(
            entries,
            "pure_alpha_aalpha_temperature",
            case_id,
            "richardson_real_value_path",
            actual,
            richardson.reference,
            labels,
        )
        dimensionless = calculate_pure_dimensionless_parameter_derivatives(
            component, temperature, synthetic_state.pressure_pa
        )
        complex_pressure = complex_step_pressure(synthetic_state)
        for family, label, actual_value, reference_value in (
            (
                "A_derivatives",
                "pure_A_P",
                dimensionless.A_pressure_derivative_per_pa,
                complex_pressure.A.imag / COMPLEX_STEP,
            ),
            (
                "B_derivatives",
                "pure_B_P",
                dimensionless.B_pressure_derivative_per_pa,
                complex_pressure.B.imag / COMPLEX_STEP,
            ),
            (
                "A_derivatives",
                "pure_A_lnP",
                dimensionless.A_log_pressure_derivative,
                synthetic_state.pressure_pa * complex_pressure.A.imag / COMPLEX_STEP,
            ),
            (
                "B_derivatives",
                "pure_B_lnP",
                dimensionless.B_log_pressure_derivative,
                synthetic_state.pressure_pa * complex_pressure.B.imag / COMPLEX_STEP,
            ),
            (
                "A_derivatives",
                "pure_A_T",
                dimensionless.A_temperature_derivative_per_k,
                complex_values.A.imag / COMPLEX_STEP,
            ),
            (
                "B_derivatives",
                "pure_B_T",
                dimensionless.B_temperature_derivative_per_k,
                complex_values.B.imag / COMPLEX_STEP,
            ),
        ):
            entries.append(
                _entry(
                    family,
                    f"{case_id}:{label}",
                    "complex_step",
                    actual_value,
                    reference_value,
                )
            )


def _state_entries(
    state: VerificationState,
    entries: list[VerificationEntry],
    exclusions: list[tuple[str, str]],
) -> None:
    baseline = ordinary_state(state)
    parameters = baseline.parameters
    parameter = calculate_mixture_parameter_derivatives(
        parameters, reference_component_index=state.reference_component_index
    )
    fugacity = calculate_fixed_root_mixture_fugacity_derivatives(
        parameters,
        baseline.root,
        reference_component_index=state.reference_component_index,
    )
    if not fugacity.applicable:
        exclusions.append((state.case_id, "production_root_derivative_not_applicable"))
        return
    count = len(state.components)
    pair_labels = tuple(f"pair_T[{i},{j}]" for i in range(count) for j in range(count))
    sum_labels = tuple(f"S_T[{i}]" for i in range(count))
    temperature_labels = (
        *pair_labels,
        *sum_labels,
        "a_mix_T",
        "b_mix_T",
        "A_T",
        "B_T",
    )
    actual_temperature = (
        *_flatten(parameter.pair_attraction_temperature_derivatives),
        *parameter.component_attraction_sum_temperature_derivatives,
        parameter.a_alpha_mix_temperature_derivative,
        parameter.b_mix_temperature_derivative,
        parameter.A_mix_temperature_derivative_per_k,
        parameter.B_mix_temperature_derivative_per_k,
    )
    complex_temperature = complex_step_temperature(state)
    complex_temperature_reference = (
        *(
            value.imag / COMPLEX_STEP
            for row in complex_temperature.pair_attraction
            for value in row
        ),
        *(value.imag / COMPLEX_STEP for value in complex_temperature.attraction_sums),
        complex_temperature.a_mix.imag / COMPLEX_STEP,
        complex_temperature.b_mix.imag / COMPLEX_STEP,
        complex_temperature.A.imag / COMPLEX_STEP,
        complex_temperature.B.imag / COMPLEX_STEP,
    )
    family_by_temperature_index = (
        *("mixing_temperature" for _ in pair_labels),
        *("mixing_temperature" for _ in sum_labels),
        "mixing_temperature",
        "mixing_temperature",
        "A_derivatives",
        "B_derivatives",
    )
    for family, actual, reference, label in zip(
        family_by_temperature_index,
        actual_temperature,
        complex_temperature_reference,
        temperature_labels,
        strict=True,
    ):
        entries.append(
            _entry(
                family, f"{state.case_id}:{label}", "complex_step", actual, reference
            )
        )
    try:
        temperature_fd = temperature_richardson(state, baseline, _temperature_values)
    except RootTrackingError as error:
        exclusions.append((state.case_id, str(error)))
    else:
        for family, actual, reference, label in zip(
            family_by_temperature_index,
            actual_temperature,
            temperature_fd.reference,
            temperature_labels,
            strict=True,
        ):
            entries.append(
                _entry(
                    family, f"{state.case_id}:{label}", "richardson", actual, reference
                )
            )

    complex_pressure = complex_step_pressure(state)
    pressure_actual = (
        parameter.A_mix_pressure_derivative_per_pa,
        parameter.B_mix_pressure_derivative_per_pa,
    )
    pressure_reference = (
        complex_pressure.A.imag / COMPLEX_STEP,
        complex_pressure.B.imag / COMPLEX_STEP,
    )
    entries.append(
        _entry(
            "A_derivatives",
            f"{state.case_id}:A_P",
            "complex_step",
            pressure_actual[0],
            pressure_reference[0],
        )
    )
    entries.append(
        _entry(
            "B_derivatives",
            f"{state.case_id}:B_P",
            "complex_step",
            pressure_actual[1],
            pressure_reference[1],
        )
    )
    pressure_fd = pressure_richardson(state, baseline, _parameter_values)
    entries.append(
        _entry(
            "A_derivatives",
            f"{state.case_id}:A_P",
            "richardson",
            pressure_actual[0],
            pressure_fd.reference[0],
        )
    )
    entries.append(
        _entry(
            "B_derivatives",
            f"{state.case_id}:B_P",
            "richardson",
            pressure_actual[1],
            pressure_fd.reference[1],
        )
    )
    log_pressure_fd = log_pressure_richardson(state, baseline, _parameter_values)
    entries.append(
        _entry(
            "A_derivatives",
            f"{state.case_id}:A_lnP",
            "richardson",
            parameter.A_mix_log_pressure_derivative,
            log_pressure_fd.reference[0],
        )
    )
    entries.append(
        _entry(
            "B_derivatives",
            f"{state.case_id}:B_lnP",
            "richardson",
            parameter.B_mix_log_pressure_derivative,
            log_pressure_fd.reference[1],
        )
    )

    pressure_root_fd = pressure_richardson(state, baseline, _root_and_log_phi)
    log_pressure_root_fd = log_pressure_richardson(state, baseline, _root_and_log_phi)
    temperature_root_fd = temperature_richardson(state, baseline, _root_and_log_phi)
    pressure_z = fugacity.pressure_root_derivative.derivative
    temperature_z = fugacity.temperature_root_derivative.derivative
    if pressure_z is None or temperature_z is None:
        raise RuntimeError("applicable derivative result omitted a root derivative")
    entries.append(
        _entry(
            "Z_pressure",
            f"{state.case_id}:Z_P",
            "richardson_root_continuation",
            pressure_z,
            pressure_root_fd.reference[0],
        )
    )
    entries.append(
        _entry(
            "Z_pressure",
            f"{state.case_id}:Z_lnP",
            "richardson_root_continuation",
            state.pressure_pa * pressure_z,
            log_pressure_root_fd.reference[0],
        )
    )
    entries.append(
        _entry(
            "Z_temperature",
            f"{state.case_id}:Z_T",
            "richardson_root_continuation",
            temperature_z,
            temperature_root_fd.reference[0],
        )
    )
    _record_cubic_identity(
        entries,
        state.case_id,
        "P",
        baseline.root,
        parameters.A_mix,
        parameters.B_mix,
        parameter.A_mix_pressure_derivative_per_pa,
        parameter.B_mix_pressure_derivative_per_pa,
        pressure_z,
    )
    _record_cubic_identity(
        entries,
        state.case_id,
        "T",
        baseline.root,
        parameters.A_mix,
        parameters.B_mix,
        parameter.A_mix_temperature_derivative_per_k,
        parameter.B_mix_temperature_derivative_per_k,
        temperature_z,
    )

    if (
        fugacity.log_fugacity_pressure_derivatives_per_pa is None
        or fugacity.log_fugacity_log_pressure_derivatives is None
        or fugacity.log_fugacity_temperature_derivatives_per_k is None
    ):
        raise RuntimeError("applicable fugacity result omitted derivatives")
    component_labels = tuple(component.name for component in state.components)
    _append_vector_entries(
        entries,
        "lnphi_pressure",
        state.case_id,
        "richardson_root_continuation",
        fugacity.log_fugacity_pressure_derivatives_per_pa,
        pressure_root_fd.reference[1:],
        component_labels,
    )
    _append_vector_entries(
        entries,
        "lnphi_pressure",
        f"{state.case_id}:lnP",
        "richardson_root_continuation",
        fugacity.log_fugacity_log_pressure_derivatives,
        log_pressure_root_fd.reference[1:],
        component_labels,
    )
    _append_vector_entries(
        entries,
        "lnphi_temperature",
        state.case_id,
        "richardson_root_continuation",
        fugacity.log_fugacity_temperature_derivatives_per_k,
        temperature_root_fd.reference[1:],
        component_labels,
    )

    reference_index = parameter.reference_component_index
    for column, independent_index in enumerate(parameter.independent_component_indices):
        coordinate_id = f"u[{independent_index}|r={reference_index}]"
        try:
            composition_fd = composition_richardson(
                state, baseline, independent_index, reference_index, _composition_values
            )
            composition_root_fd = composition_richardson(
                state, baseline, independent_index, reference_index, _root_and_log_phi
            )
        except RootTrackingError as error:
            exclusions.append((f"{state.case_id}:{coordinate_id}", str(error)))
            continue
        complex_composition = complex_step_composition(
            state, independent_index, reference_index
        )
        actual_composition = (
            parameter.a_alpha_mix_composition_derivatives[column],
            parameter.b_mix_composition_derivatives[column],
            parameter.A_mix_composition_derivatives[column],
            parameter.B_mix_composition_derivatives[column],
            *(
                row[column]
                for row in parameter.component_attraction_sum_composition_derivatives
            ),
        )
        complex_composition_reference = (
            complex_composition.a_mix.imag / COMPLEX_STEP,
            complex_composition.b_mix.imag / COMPLEX_STEP,
            complex_composition.A.imag / COMPLEX_STEP,
            complex_composition.B.imag / COMPLEX_STEP,
            *(
                value.imag / COMPLEX_STEP
                for value in complex_composition.attraction_sums
            ),
        )
        composition_labels = (
            "a_mix_u",
            "b_mix_u",
            "A_u",
            "B_u",
            *(f"S[{i}]_u" for i in range(count)),
        )
        composition_families = (
            "mixing_composition",
            "mixing_composition",
            "A_derivatives",
            "B_derivatives",
            *("mixing_composition" for _ in range(count)),
        )
        for route, reference_values in (
            ("complex_step", complex_composition_reference),
            ("richardson", composition_fd.reference),
        ):
            for family, actual, reference, label in zip(
                composition_families,
                actual_composition,
                reference_values,
                composition_labels,
                strict=True,
            ):
                entries.append(
                    _entry(
                        family,
                        f"{state.case_id}:{coordinate_id}:{label}",
                        route,
                        actual,
                        reference,
                    )
                )
        root_derivative = fugacity.composition_root_derivatives[column].derivative
        if root_derivative is None:
            raise RuntimeError("applicable composition root derivative omitted value")
        entries.append(
            _entry(
                "Z_composition",
                f"{state.case_id}:{coordinate_id}",
                "richardson_root_continuation",
                root_derivative,
                composition_root_fd.reference[0],
            )
        )
        _record_cubic_identity(
            entries,
            state.case_id,
            coordinate_id,
            baseline.root,
            parameters.A_mix,
            parameters.B_mix,
            parameter.A_mix_composition_derivatives[column],
            parameter.B_mix_composition_derivatives[column],
            root_derivative,
        )
        if fugacity.log_fugacity_composition_derivatives is None:
            raise RuntimeError("applicable fugacity result omitted composition matrix")
        analytical_log_phi = tuple(
            row[column] for row in fugacity.log_fugacity_composition_derivatives
        )
        _append_vector_entries(
            entries,
            "lnphi_composition",
            f"{state.case_id}:{coordinate_id}",
            "richardson_root_continuation",
            analytical_log_phi,
            composition_root_fd.reference[1:],
            component_labels,
        )


def _near_singular_study() -> tuple[NearSingularObservation, ...]:
    rows: list[NearSingularObservation] = []
    B = 0.0778
    for A in (0.456, 0.457, 0.4572, 0.45723, 0.45724):
        root = calculate_compressibility_roots(A, B)[0]
        result = calculate_fixed_root_compressibility_derivative(
            root,
            A,
            B,
            1.0,
            0.0,
            derivative_variable="A",
            derivative_units="dimensionless",
        )
        if not result.applicable or result.derivative is None:
            raise RuntimeError("resolved near-singular study root became inapplicable")
        reference = richardson_vector(
            lambda delta, current_A=A: (
                calculate_compressibility_roots(current_A + delta, B)[0],
            ),
            1e-7,
        ).reference[0]
        rows.append(
            NearSingularObservation(
                A=A,
                B=B,
                root=root,
                absolute_cubic_partial_z=abs(result.cubic_partial_z),
                derivative_magnitude=abs(result.derivative),
                reference_derivative=reference,
                absolute_error=abs(result.derivative - reference),
            )
        )
    exact_B = 0.07779607390388846
    exact_A = 0.4572355289213822
    exact_root = (1.0 - exact_B) / 3.0
    exact = calculate_fixed_root_compressibility_derivative(
        exact_root,
        exact_A,
        exact_B,
        1.0,
        0.0,
        derivative_variable="A",
        derivative_units="dimensionless",
    )
    if exact.applicable or exact.derivative is not None:
        raise RuntimeError("exact repeated root did not return non-applicability")
    return tuple(rows)


def run_verification_matrix() -> VerificationReport:
    """Run the deterministic independent verification matrix."""

    entries: list[VerificationEntry] = []
    exclusions: list[tuple[str, str]] = []
    _pure_entries(entries)
    for state in EOS_STATES:
        try:
            _state_entries(state, entries, exclusions)
        except RootTrackingError as error:
            exclusions.append((state.case_id, str(error)))
    if not all(
        isfinite(entry.analytical)
        and isfinite(entry.reference)
        and isfinite(entry.absolute_error)
        for entry in entries
    ):
        raise RuntimeError("verification matrix contains a non-finite value")
    explicit_ids = tuple(case_id for case_id, _, _ in PURE_TEMPERATURE_CASES) + tuple(
        state.case_id for state in EOS_STATES
    )
    return VerificationReport(
        explicit_case_ids=explicit_ids,
        entries=tuple(entries),
        exclusions=tuple(exclusions),
        near_singular=_near_singular_study(),
    )
