"""Focused Module 13 tests for analytical fixed-root PR derivatives."""

from dataclasses import FrozenInstanceError
from math import isfinite, sqrt

import pytest

from pvt_phase_simulator.eos import derivatives as derivatives_module
from pvt_phase_simulator.eos.derivatives import (
    FixedRootCompressibilityDerivative,
    FixedRootMixtureFugacityDerivatives,
    MixtureParameterDerivatives,
    PureComponentTemperatureDerivatives,
    PureDimensionlessParameterDerivatives,
    calculate_fixed_root_compressibility_derivative,
    calculate_fixed_root_mixture_fugacity_derivatives,
    calculate_mixture_parameter_derivatives,
    calculate_pure_component_temperature_derivatives,
    calculate_pure_dimensionless_parameter_derivatives,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    PengRobinsonMixtureParameters,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_alpha,
    calculate_compressibility_roots,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)


def _mixture(
    components: tuple[Component, ...], fractions: tuple[float, ...]
) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(components, fractions, strict=True)
        )
    )


def _parameters(
    components: tuple[Component, ...] = (METHANE, ETHANE, PROPANE),
    fractions: tuple[float, ...] = (0.5, 0.3, 0.2),
    temperature_k: float = 280.0,
    pressure_pa: float = 3_000_000.0,
    interactions: BinaryInteractionMapping | None = None,
) -> PengRobinsonMixtureParameters:
    return calculate_peng_robinson_mixture_parameters(
        _mixture(components, fractions),
        temperature_k,
        pressure_pa,
        interactions,
    )


def _continued_root(
    parameters: PengRobinsonMixtureParameters, reference_root: float
) -> float:
    return min(
        calculate_compressibility_roots(parameters.A_mix, parameters.B_mix),
        key=lambda root: abs(root - reference_root),
    )


def _log_phi_on_continued_root(
    parameters: PengRobinsonMixtureParameters,
    reference_root: float,
    interactions: BinaryInteractionMapping | None = None,
) -> tuple[float, ...]:
    root = _continued_root(parameters, reference_root)
    return tuple(
        item.log_fugacity_coefficient
        for item in calculate_mixture_fugacity_coefficients(
            parameters, root, interactions
        )
    )


class TestDerivativeApiStructure:
    def test_module_states_the_fixed_root_contract_verbatim(self) -> None:
        assert derivatives_module.__doc__ is not None
        assert (
            "Derivatives are valid locally on a fixed physical root and do not "
            "include root\nswitching or branch-selection discontinuities."
            in derivatives_module.__doc__
        )

    def test_result_structures_are_frozen_and_explicit(self) -> None:
        pure = calculate_pure_component_temperature_derivatives(METHANE, 250.0)
        dimensionless = calculate_pure_dimensionless_parameter_derivatives(
            METHANE, 250.0, 2_000_000.0
        )
        parameters = _parameters()
        mixture = calculate_mixture_parameter_derivatives(parameters)
        root = max(calculate_compressibility_roots(parameters.A_mix, parameters.B_mix))
        fugacity = calculate_fixed_root_mixture_fugacity_derivatives(parameters, root)
        assert isinstance(pure, PureComponentTemperatureDerivatives)
        assert isinstance(dimensionless, PureDimensionlessParameterDerivatives)
        assert isinstance(mixture, MixtureParameterDerivatives)
        assert isinstance(fugacity, FixedRootMixtureFugacityDerivatives)
        with pytest.raises(FrozenInstanceError):
            pure.alpha = 0.0  # type: ignore[misc]

    def test_units_and_simplex_coordinate_metadata_are_explicit(self) -> None:
        parameters = _parameters()
        derivatives = calculate_mixture_parameter_derivatives(
            parameters, reference_component_index=1
        )
        assert derivatives.reference_component_index == 1
        assert derivatives.independent_component_indices == (0, 2)
        root = max(calculate_compressibility_roots(parameters.A_mix, parameters.B_mix))
        result = calculate_fixed_root_mixture_fugacity_derivatives(
            parameters, root, reference_component_index=1
        )
        assert result.pressure_root_derivative.derivative_units == "Pa^-1"
        assert result.temperature_root_derivative.derivative_units == "K^-1"
        assert all(
            item.derivative_units == "mole-fraction^-1"
            for item in result.composition_root_derivatives
        )

    def test_binary_interaction_provenance_is_preserved(self) -> None:
        interactions = {
            ("Methane", "Ethane"): 0.02,
            ("Ethane", "Methane"): 0.02,
            ("Methane", "Propane"): 0.0,
            ("Propane", "Methane"): 0.0,
        }
        parameters = _parameters(interactions=interactions)
        calculate_mixture_parameter_derivatives(parameters, interactions)
        with pytest.raises(ValueError, match="provenance"):
            calculate_mixture_parameter_derivatives(
                parameters,
                {
                    ("Methane", "Ethane"): 0.02,
                    ("Ethane", "Methane"): 0.02,
                },
            )


class TestAlgebraicDerivativeIdentities:
    @pytest.mark.parametrize(
        ("component", "temperature_k"),
        [
            (METHANE, 150.0),
            (METHANE, 0.99 * METHANE.critical_temperature_k),
            (METHANE, 350.0),
            (ETHANE, 240.0),
            (ETHANE, 0.99 * ETHANE.critical_temperature_k),
            (ETHANE, 450.0),
            (PROPANE, 300.0),
            (PROPANE, 0.99 * PROPANE.critical_temperature_k),
            (PROPANE, 550.0),
        ],
    )
    def test_pure_alpha_temperature_formula(
        self, component: Component, temperature_k: float
    ) -> None:
        result = calculate_pure_component_temperature_derivatives(
            component, temperature_k
        )
        expected = -(
            result.kappa
            * (1.0 + result.kappa * (1.0 - sqrt(result.reduced_temperature)))
            / (component.critical_temperature_k * sqrt(result.reduced_temperature))
        )
        assert result.alpha_temperature_derivative_per_k == pytest.approx(
            expected, rel=2e-15
        )
        assert result.a_alpha_temperature_derivative == pytest.approx(
            result.a * expected, rel=2e-15
        )

    @pytest.mark.parametrize("pressure_pa", [100_000.0, 3_000_000.0, 10_000_000.0])
    def test_dimensionless_pressure_and_log_pressure_identities(
        self, pressure_pa: float
    ) -> None:
        result = calculate_pure_dimensionless_parameter_derivatives(
            PROPANE, 330.0, pressure_pa
        )
        assert result.A_pressure_derivative_per_pa == result.A / pressure_pa
        assert result.B_pressure_derivative_per_pa == result.B / pressure_pa
        assert result.A_log_pressure_derivative == pytest.approx(
            pressure_pa * result.A_pressure_derivative_per_pa, rel=2e-16
        )
        assert result.B_log_pressure_derivative == pytest.approx(
            pressure_pa * result.B_pressure_derivative_per_pa, rel=2e-16
        )

    def test_mixing_rule_derivatives_are_symmetric_exact_sums(self) -> None:
        parameters = _parameters()
        result = calculate_mixture_parameter_derivatives(parameters)
        count = len(result.component_names)
        for i in range(count):
            for j in range(count):
                assert (
                    result.pair_attraction_parameters[i][j]
                    == (result.pair_attraction_parameters[j][i])
                )
                assert (
                    result.pair_attraction_temperature_derivatives[i][j]
                    == (result.pair_attraction_temperature_derivatives[j][i])
                )
        assert result.b_mix_temperature_derivative == 0.0
        assert result.a_alpha_mix_temperature_derivative == pytest.approx(
            sum(
                parameters.component_parameters[i].mole_fraction
                * parameters.component_parameters[j].mole_fraction
                * result.pair_attraction_temperature_derivatives[i][j]
                for i in range(count)
                for j in range(count)
            ),
            rel=2e-15,
        )

    @pytest.mark.parametrize("root_index", [0, -1])
    def test_implicit_cubic_total_derivative_residual_is_zero(
        self, root_index: int
    ) -> None:
        parameters = _parameters(
            components=(METHANE, PROPANE),
            fractions=(0.6, 0.4),
            temperature_k=250.0,
            pressure_pa=3_000_000.0,
        )
        root = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)[
            root_index
        ]
        parameter = calculate_mixture_parameter_derivatives(parameters)
        result = calculate_fixed_root_compressibility_derivative(
            root,
            parameters.A_mix,
            parameters.B_mix,
            parameter.A_mix_temperature_derivative_per_k,
            parameter.B_mix_temperature_derivative_per_k,
            derivative_variable="temperature_k",
            derivative_units="K^-1",
        )
        assert result.applicable
        assert result.derivative is not None
        assert (
            result.parameter_partial + result.cubic_partial_z * result.derivative
            == (pytest.approx(0.0, abs=2e-18))
        )

    def test_fugacity_pressure_log_pressure_chain_rule_is_exact(self) -> None:
        parameters = _parameters(pressure_pa=8_000_000.0)
        root = max(calculate_compressibility_roots(parameters.A_mix, parameters.B_mix))
        result = calculate_fixed_root_mixture_fugacity_derivatives(parameters, root)
        assert result.applicable
        assert result.log_fugacity_pressure_derivatives_per_pa is not None
        assert result.log_fugacity_log_pressure_derivatives is not None
        assert result.log_fugacity_log_pressure_derivatives == tuple(
            parameters.pressure_pa * value
            for value in result.log_fugacity_pressure_derivatives_per_pa
        )

    def test_pure_limit_has_no_composition_columns(self) -> None:
        parameters = _parameters(
            components=(ETHANE,), fractions=(1.0,), temperature_k=330.0
        )
        root = max(calculate_compressibility_roots(parameters.A_mix, parameters.B_mix))
        result = calculate_fixed_root_mixture_fugacity_derivatives(parameters, root)
        assert result.applicable
        assert result.parameter_derivatives.independent_component_indices == ()
        assert result.composition_root_derivatives == ()
        assert result.log_fugacity_composition_derivatives == ((),)

    def test_zero_fraction_derivatives_remain_finite(self) -> None:
        parameters = _parameters(fractions=(0.7, 0.0, 0.3))
        result = calculate_mixture_parameter_derivatives(parameters)
        values = (
            *result.a_alpha_mix_composition_derivatives,
            *result.b_mix_composition_derivatives,
            *result.A_mix_composition_derivatives,
            *result.B_mix_composition_derivatives,
        )
        assert all(isfinite(value) for value in values)

    def test_component_permutation_preserves_named_derivatives(self) -> None:
        forward = _parameters(fractions=(0.5, 0.3, 0.2))
        reverse = _parameters(
            components=(PROPANE, ETHANE, METHANE), fractions=(0.2, 0.3, 0.5)
        )
        forward_root = max(
            calculate_compressibility_roots(forward.A_mix, forward.B_mix)
        )
        reverse_root = max(
            calculate_compressibility_roots(reverse.A_mix, reverse.B_mix)
        )
        first = calculate_fixed_root_mixture_fugacity_derivatives(
            forward, forward_root, reference_component_index=2
        )
        second = calculate_fixed_root_mixture_fugacity_derivatives(
            reverse, reverse_root, reference_component_index=0
        )
        assert first.applicable and second.applicable
        assert first.log_fugacity_temperature_derivatives_per_k is not None
        assert second.log_fugacity_temperature_derivatives_per_k is not None
        by_name = dict(
            zip(
                second.component_names,
                second.log_fugacity_temperature_derivatives_per_k,
                strict=True,
            )
        )
        assert first.log_fugacity_temperature_derivatives_per_k == pytest.approx(
            tuple(by_name[name] for name in first.component_names), rel=2e-13
        )

    @pytest.mark.parametrize(
        ("components", "fractions", "pressure_pa", "root_index"),
        [
            ((METHANE, ETHANE), (0.7, 0.3), 100_000.0, -1),
            ((METHANE, ETHANE), (0.7, 0.3), 8_000_000.0, -1),
            ((METHANE, PROPANE), (0.6, 0.4), 3_000_000.0, 0),
            ((METHANE, PROPANE), (0.6, 0.4), 3_000_000.0, -1),
        ],
    )
    def test_binary_root_and_fugacity_derivatives_are_finite(
        self,
        components: tuple[Component, ...],
        fractions: tuple[float, ...],
        pressure_pa: float,
        root_index: int,
    ) -> None:
        parameters = _parameters(
            components=components,
            fractions=fractions,
            temperature_k=250.0,
            pressure_pa=pressure_pa,
        )
        root = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)[
            root_index
        ]
        result = calculate_fixed_root_mixture_fugacity_derivatives(parameters, root)
        assert result.applicable
        assert result.log_fugacity_pressure_derivatives_per_pa is not None
        assert result.log_fugacity_temperature_derivatives_per_k is not None
        assert all(
            isfinite(value)
            for value in (
                *result.log_fugacity_pressure_derivatives_per_pa,
                *result.log_fugacity_temperature_derivatives_per_k,
            )
        )


class TestCentralDifferenceSanity:
    @pytest.mark.parametrize("relative_step", [1e-3, 5e-4])
    def test_pure_alpha_temperature_derivative(self, relative_step: float) -> None:
        temperature = 280.0
        step = relative_step * temperature
        analytical = calculate_pure_component_temperature_derivatives(
            ETHANE, temperature
        )
        central = (
            calculate_alpha(
                temperature + step,
                ETHANE.critical_temperature_k,
                ETHANE.acentric_factor,
            )
            - calculate_alpha(
                temperature - step,
                ETHANE.critical_temperature_k,
                ETHANE.acentric_factor,
            )
        ) / (2.0 * step)
        assert analytical.alpha_temperature_derivative_per_k == pytest.approx(
            central, rel=2e-7
        )

    @pytest.mark.parametrize("relative_step", [1e-4, 5e-5])
    def test_mixture_parameter_temperature_derivatives(
        self, relative_step: float
    ) -> None:
        temperature = 280.0
        step = relative_step * temperature
        base = _parameters(temperature_k=temperature)
        analytical = calculate_mixture_parameter_derivatives(base)
        plus = _parameters(temperature_k=temperature + step)
        minus = _parameters(temperature_k=temperature - step)
        assert analytical.a_alpha_mix_temperature_derivative == pytest.approx(
            (plus.a_alpha_mix - minus.a_alpha_mix) / (2.0 * step), rel=2e-8
        )
        assert analytical.A_mix_temperature_derivative_per_k == pytest.approx(
            (plus.A_mix - minus.A_mix) / (2.0 * step), rel=3e-8
        )
        assert analytical.B_mix_temperature_derivative_per_k == pytest.approx(
            (plus.B_mix - minus.B_mix) / (2.0 * step), rel=2e-8
        )

    @pytest.mark.parametrize("relative_step", [1e-4, 5e-5])
    def test_fixed_root_pressure_and_fugacity_derivatives(
        self, relative_step: float
    ) -> None:
        pressure = 3_000_000.0
        step = relative_step * pressure
        base = _parameters(pressure_pa=pressure)
        root = max(calculate_compressibility_roots(base.A_mix, base.B_mix))
        analytical = calculate_fixed_root_mixture_fugacity_derivatives(base, root)
        plus = _parameters(pressure_pa=pressure + step)
        minus = _parameters(pressure_pa=pressure - step)
        root_plus = _continued_root(plus, root)
        root_minus = _continued_root(minus, root)
        assert analytical.pressure_root_derivative.derivative is not None
        assert analytical.pressure_root_derivative.derivative == pytest.approx(
            (root_plus - root_minus) / (2.0 * step), rel=3e-8
        )
        plus_phi = _log_phi_on_continued_root(plus, root)
        minus_phi = _log_phi_on_continued_root(minus, root)
        central = tuple(
            (high - low) / (2.0 * step)
            for high, low in zip(plus_phi, minus_phi, strict=True)
        )
        assert analytical.log_fugacity_pressure_derivatives_per_pa == pytest.approx(
            central, rel=8e-8, abs=2e-15
        )

    @pytest.mark.parametrize("relative_step", [1e-4, 5e-5])
    def test_fixed_root_temperature_and_fugacity_derivatives(
        self, relative_step: float
    ) -> None:
        temperature = 280.0
        step = relative_step * temperature
        base = _parameters(temperature_k=temperature)
        root = max(calculate_compressibility_roots(base.A_mix, base.B_mix))
        analytical = calculate_fixed_root_mixture_fugacity_derivatives(base, root)
        plus = _parameters(temperature_k=temperature + step)
        minus = _parameters(temperature_k=temperature - step)
        assert analytical.temperature_root_derivative.derivative is not None
        assert analytical.temperature_root_derivative.derivative == pytest.approx(
            (_continued_root(plus, root) - _continued_root(minus, root)) / (2.0 * step),
            rel=2e-7,
        )
        central = tuple(
            (high - low) / (2.0 * step)
            for high, low in zip(
                _log_phi_on_continued_root(plus, root),
                _log_phi_on_continued_root(minus, root),
                strict=True,
            )
        )
        assert analytical.log_fugacity_temperature_derivatives_per_k == pytest.approx(
            central, rel=2e-6, abs=2e-12
        )

    @pytest.mark.parametrize("step", [1e-5, 5e-6])
    def test_simplex_composition_fugacity_derivatives(self, step: float) -> None:
        fractions = (0.5, 0.3, 0.2)
        base = _parameters(fractions=fractions)
        root = max(calculate_compressibility_roots(base.A_mix, base.B_mix))
        analytical = calculate_fixed_root_mixture_fugacity_derivatives(base, root)
        assert analytical.log_fugacity_composition_derivatives is not None
        for column, independent in enumerate((0, 1)):
            plus_fractions = list(fractions)
            minus_fractions = list(fractions)
            plus_fractions[independent] += step
            plus_fractions[2] -= step
            minus_fractions[independent] -= step
            minus_fractions[2] += step
            plus = _parameters(fractions=tuple(plus_fractions))
            minus = _parameters(fractions=tuple(minus_fractions))
            central = tuple(
                (high - low) / (2.0 * step)
                for high, low in zip(
                    _log_phi_on_continued_root(plus, root),
                    _log_phi_on_continued_root(minus, root),
                    strict=True,
                )
            )
            assert tuple(
                row[column] for row in analytical.log_fugacity_composition_derivatives
            ) == pytest.approx(central, rel=2e-8, abs=2e-10)

    def test_near_pure_composition_remains_accurate(self) -> None:
        fractions = (0.999_999, 0.000_001)
        step = 1e-7
        base = _parameters(
            components=(METHANE, PROPANE), fractions=fractions, pressure_pa=1_000_000.0
        )
        root = max(calculate_compressibility_roots(base.A_mix, base.B_mix))
        analytical = calculate_fixed_root_mixture_fugacity_derivatives(base, root)
        plus = _parameters(
            components=(METHANE, PROPANE),
            fractions=(fractions[0] + step, fractions[1] - step),
            pressure_pa=1_000_000.0,
        )
        minus = _parameters(
            components=(METHANE, PROPANE),
            fractions=(fractions[0] - step, fractions[1] + step),
            pressure_pa=1_000_000.0,
        )
        central = tuple(
            (high - low) / (2.0 * step)
            for high, low in zip(
                _log_phi_on_continued_root(plus, root),
                _log_phi_on_continued_root(minus, root),
                strict=True,
            )
        )
        assert analytical.log_fugacity_composition_derivatives is not None
        assert tuple(
            row[0] for row in analytical.log_fugacity_composition_derivatives
        ) == pytest.approx(central, rel=2e-7, abs=2e-9)


class TestDerivativeSingularityHandling:
    def test_exact_multiple_root_returns_structured_non_applicability(self) -> None:
        B = 0.07779607390388846
        A = 0.4572355289213822
        root = (1.0 - B) / 3.0
        result = calculate_fixed_root_compressibility_derivative(
            root,
            A,
            B,
            1.0,
            0.0,
            derivative_variable="A",
            derivative_units="dimensionless",
        )
        assert isinstance(result, FixedRootCompressibilityDerivative)
        assert not result.applicable
        assert result.derivative is None
        assert result.failure_reason is not None
        assert "multiple" in result.failure_reason

    def test_moderately_close_root_remains_explicitly_applicable(self) -> None:
        A = 0.4572
        B = 0.0778
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
        assert result.applicable
        assert result.derivative is not None
        assert abs(result.derivative) > 100.0

    def test_invalid_nonroot_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="cubic"):
            calculate_fixed_root_compressibility_derivative(
                0.5,
                0.2,
                0.02,
                1.0,
                0.0,
                derivative_variable="A",
                derivative_units="dimensionless",
            )
