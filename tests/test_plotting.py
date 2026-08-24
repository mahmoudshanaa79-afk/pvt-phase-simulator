"""Structural and scientific-invariant tests for Module 21 Plotly figures."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import pvt_phase_simulator.eos.phase_envelope as envelope_module
from pvt_phase_simulator.eos.critical_point import (
    CriticalPointScanSettings,
    CriticalPointStatus,
    scan_mixture_criticality,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeBranchKind,
    EnvelopeContinuationSettings,
    calculate_phase_envelope,
)
from pvt_phase_simulator.eos.pseudo_arclength import (
    PseudoArclengthSettings,
    trace_pseudo_arclength_branch,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)
from pvt_phase_simulator.plotting import (
    CriticalityGrid,
    PhaseBehaviorPoint,
    PhaseEnvelopePlotData,
    convert_pressure,
    criticality_grid_from_scan,
    load_validation_plot_records,
    phase_envelope_plot_data,
    plot_binary_xy,
    plot_critical_solver_conditioning,
    plot_critical_solver_convergence,
    plot_critical_solver_path,
    plot_criticality_map,
    plot_phase_compositions,
    plot_phase_envelope,
    plot_pseudo_arclength_diagnostic,
    plot_pseudo_arclength_trace,
    plot_validation_composition_parity,
    plot_validation_pressure_error,
    plot_validation_pressure_parity,
    plot_validation_retrospective_diagnostics,
    plot_validation_status,
    validation_plot_records_from_dataframe,
)

VALIDATION_PATH = Path("docs/validation/module17_vle_validation.csv")


def _ch4_c3() -> FluidMixture:
    return FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(PROPANE, 0.5))
    )


def _ch4_c2() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5)))


def _synthetic_envelope() -> PhaseEnvelopePlotData:
    return PhaseEnvelopePlotData(
        bubble_points=(
            PhaseBehaviorPoint(
                280.0,
                4.0e6,
                liquid_composition=(0.4, 0.6),
                vapor_composition=(0.8, 0.2),
            ),
            PhaseBehaviorPoint(
                300.0,
                6.0e6,
                liquid_composition=(0.5, 0.5),
                vapor_composition=(0.75, 0.25),
            ),
        ),
        dew_points=(
            PhaseBehaviorPoint(
                280.0,
                2.0e6,
                liquid_composition=(0.2, 0.8),
                vapor_composition=(0.6, 0.4),
            ),
            PhaseBehaviorPoint(
                300.0,
                5.0e6,
                liquid_composition=(0.3, 0.7),
                vapor_composition=(0.55, 0.45),
            ),
        ),
        component_names=("Methane", "Propane"),
        composition=(0.5, 0.5),
        bubble_termination="near_critical",
        dew_termination="branch_lost",
    )


@pytest.fixture(scope="module")
def critical_result():
    return solve_mixture_critical_point(_ch4_c3(), 320.0, 8.5e6)


@pytest.fixture(scope="module")
def real_envelope():
    settings = EnvelopeContinuationSettings(
        target_temperature_k=205.0,
        initial_temperature_step_k=5.0,
        maximum_points=3,
    )
    return calculate_phase_envelope(_ch4_c2(), settings, settings, 200.0, 200.0)


@pytest.fixture(scope="module")
def pseudo_result():
    return trace_pseudo_arclength_branch(
        _ch4_c2(),
        EnvelopeBranchKind.BUBBLE,
        PseudoArclengthSettings(initial_temperature_step_k=2.0, maximum_points=5),
        200.0,
    )


@pytest.fixture(scope="module")
def validation_records():
    return load_validation_plot_records(VALIDATION_PATH)


class TestUnitsAndPurePhaseEnvelope:
    @pytest.mark.parametrize(
        ("unit", "expected"),
        [("Pa", 1.0e6), ("kPa", 1.0e3), ("MPa", 1.0), ("bar", 10.0)],
    )
    def test_pressure_conversion_is_exact(self, unit: str, expected: float) -> None:
        assert convert_pressure(1.0e6, unit) == expected

    def test_pressure_conversion_preserves_container_and_input(self) -> None:
        source_list = [1.0e5, 2.0e5]
        source_tuple = (1.0e5, 2.0e5)
        source_array = np.asarray((1.0e5, 2.0e5))
        original_array = source_array.copy()
        assert convert_pressure(source_list, "bar") == (1.0, 2.0)
        assert convert_pressure(source_tuple, "kPa") == (100.0, 200.0)
        converted = convert_pressure(source_array, "MPa")
        assert isinstance(converted, np.ndarray)
        assert converted == pytest.approx((0.1, 0.2))
        assert source_list == [1.0e5, 2.0e5]
        assert source_tuple == (1.0e5, 2.0e5)
        assert np.array_equal(source_array, original_array)

    def test_unsupported_pressure_unit_and_nonfinite_values_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="Pa, kPa, MPa, or bar"):
            convert_pressure(1.0, "psi")
        with pytest.raises(ValueError, match="finite"):
            convert_pressure((1.0, float("nan")), "Pa")

    def test_synthetic_branches_have_exact_fidelity_and_noncolor_styles(self) -> None:
        source = _synthetic_envelope()
        figure = plot_phase_envelope(source, pressure_unit="MPa")
        assert tuple(figure.data[0].x) == (280.0, 300.0)
        assert tuple(figure.data[0].y) == (4.0, 6.0)
        assert tuple(figure.data[1].y) == (2.0, 5.0)
        assert figure.data[0].name == "Bubble branch"
        assert figure.data[0].line.dash == "solid"
        assert figure.data[0].marker.symbol == "circle"
        assert figure.data[1].name == "Dew branch"
        assert figure.data[1].line.dash == "dash"
        assert figure.data[1].marker.symbol == "diamond"
        assert figure.layout.yaxis.title.text == "Pressure (MPa)"

    def test_termination_markers_preserve_scientific_distinction(self) -> None:
        figure = plot_phase_envelope(_synthetic_envelope())
        names = tuple(trace.name for trace in figure.data)
        assert "Bubble Near-critical termination" in names
        assert "Dew Branch-lost termination" in names
        assert all("critical point" not in name.lower() for name in names[2:])

    def test_empty_phase_envelope_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="no plottable points"):
            plot_phase_envelope(PhaseEnvelopePlotData((), ()))

    def test_failed_phase_point_has_distinct_status_semantics(self) -> None:
        source = PhaseEnvelopePlotData(
            (PhaseBehaviorPoint(300.0, 5.0e6, status="failed"),), ()
        )
        figure = plot_phase_envelope(source)
        assert len(figure.data) == 1
        assert figure.data[0].name == "Bubble branch unavailable/rejected"
        assert figure.data[0].marker.symbol == "x-open"
        assert figure.data[0].mode == "markers"

    def test_pure_renderer_does_not_call_envelope_solver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            envelope_module,
            "calculate_phase_envelope",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("solver called")
            ),
        )
        assert len(plot_phase_envelope(_synthetic_envelope()).data) == 4

    def test_same_input_has_deterministic_plotly_json(self) -> None:
        first = plot_phase_envelope(_synthetic_envelope()).to_json()
        second = plot_phase_envelope(_synthetic_envelope()).to_json()
        assert first == second

    def test_optional_provenance_is_retained_as_figure_metadata(self) -> None:
        figure = plot_phase_envelope(
            _synthetic_envelope(), metadata={"kij_policy": "default_zero"}
        )
        assert figure.layout.meta == {"kij_policy": "default_zero"}


class TestCriticalOverlayAndRealEnvelope:
    def test_certified_critical_marker_is_exact(self, critical_result) -> None:
        figure = plot_phase_envelope(
            _synthetic_envelope(),
            critical_point=critical_result,
            metadata={"model": "zero-kij Peng-Robinson"},
        )
        critical = next(
            trace for trace in figure.data if trace.name == "Certified critical point"
        )
        assert tuple(critical.x) == (321.5829183194,)
        assert tuple(critical.y) == (8.53444323606381,)
        assert "zero-kij Peng-Robinson" in critical.text[0]
        assert "composition=(0.5, 0.5)" in critical.text[0]
        assert "lambda_min" in critical.text[0]

    def test_failed_critical_result_is_not_plotted(self, critical_result) -> None:
        failed = replace(critical_result, status=CriticalPointStatus.LINE_SEARCH_FAILED)
        figure = plot_phase_envelope(_synthetic_envelope(), critical_point=failed)
        assert "Certified critical point" not in tuple(
            trace.name for trace in figure.data
        )

    def test_real_envelope_coordinates_are_source_values(self, real_envelope) -> None:
        data = phase_envelope_plot_data(real_envelope)
        figure = plot_phase_envelope(real_envelope, pressure_unit="bar")
        assert tuple(figure.data[0].x) == tuple(
            point.temperature_k for point in data.bubble_points
        )
        assert tuple(figure.data[0].y) == pytest.approx(
            tuple(point.pressure_pa / 1.0e5 for point in data.bubble_points)
        )
        assert tuple(figure.data[1].y) == pytest.approx(
            tuple(point.pressure_pa / 1.0e5 for point in data.dew_points)
        )

    def test_adapter_and_plot_do_not_mutate_result(self, real_envelope) -> None:
        before = deepcopy(real_envelope)
        plot_phase_envelope(real_envelope)
        assert real_envelope == before

    def test_composition_fraction_and_mol_percent_labels(self) -> None:
        fraction = plot_phase_compositions(_synthetic_envelope(), display="fraction")
        percent = plot_phase_compositions(_synthetic_envelope(), display="mol %")
        assert tuple(fraction.data[0].y) == (0.4, 0.5)
        assert tuple(percent.data[0].y) == (40.0, 50.0)
        assert "mole fraction" in fraction.layout.yaxis.title.text
        assert "mol %" in percent.layout.yaxis.title.text

    def test_binary_xy_uses_actual_liquid_and_vapor_data(self) -> None:
        figure = plot_binary_xy(_synthetic_envelope(), branch="dew")
        assert tuple(figure.data[0].x) == (0.2, 0.3)
        assert tuple(figure.data[0].y) == (0.6, 0.55)
        assert figure.data[1].name == "x = y"


class TestPseudoArclengthFigures:
    def test_trace_coordinates_match_result(self, pseudo_result) -> None:
        figure = plot_pseudo_arclength_trace(pseudo_result, pressure_unit="kPa")
        assert tuple(figure.data[0].x) == tuple(
            point.temperature_k for point in pseudo_result.points
        )
        assert tuple(figure.data[0].y) == pytest.approx(
            tuple(point.pressure_pa / 1.0e3 for point in pseudo_result.points)
        )

    def test_pressure_turning_annotation_is_not_called_critical(
        self, pseudo_result
    ) -> None:
        points = list(pseudo_result.points)
        points[2] = replace(points[2], pressure_turning_point=True)
        marked = replace(
            pseudo_result,
            points=tuple(points),
            pressure_turning_point_count=1,
        )
        figure = plot_pseudo_arclength_trace(marked)
        trace = next(item for item in figure.data if "Pressure turning" in item.name)
        assert trace.name == "Pressure turning point (not critical)"
        assert not any("Temperature turning" in item.name for item in figure.data)

    @pytest.mark.parametrize(
        ("metric", "label"),
        [
            ("dlnp_ds", "dln(P)/ds"),
            ("dlnt_ds", "dln(T)/ds"),
            ("step_size", "Accepted arclength step"),
            ("corrector_iterations", "Corrector iterations"),
        ],
    )
    def test_separate_diagnostic_figures(self, pseudo_result, metric, label) -> None:
        figure = plot_pseudo_arclength_diagnostic(pseudo_result, metric)
        assert figure.data[0].name == label
        assert len(figure.data[0].x) == len(pseudo_result.points)


class TestExperimentalValidationFigures:
    def test_canonical_artifact_loads_once_with_expected_count(
        self, validation_records
    ) -> None:
        assert len(validation_records) == 40
        assert {item.system_id for item in validation_records} == {"ch4_c2", "ch4_c3"}

    def test_parity_contains_only_production_predictions_and_dynamic_identity(
        self, validation_records
    ) -> None:
        figure = plot_validation_pressure_parity(
            validation_records, direction="dew", pressure_unit="MPa"
        )
        production = figure.data[0]
        identity = figure.data[1]
        expected = tuple(
            item
            for item in validation_records
            if item.dew_status == "converged"
            and item.dew_predicted_pressure_pa is not None
        )
        assert len(production.x) == len(expected)
        assert tuple(production.x) == pytest.approx(
            tuple(item.experimental_pressure_pa / 1.0e6 for item in expected)
        )
        assert tuple(production.y) == pytest.approx(
            tuple(float(item.dew_predicted_pressure_pa) / 1.0e6 for item in expected)
        )
        assert tuple(identity.x) == (
            min((*production.x, *production.y)),
            max((*production.x, *production.y)),
        )
        assert tuple(identity.x) == tuple(identity.y)
        assert "Retrospective" not in production.name

    def test_relative_error_preserves_module17_sign(self, validation_records) -> None:
        expected = next(
            item
            for item in validation_records
            if item.bubble_pressure_relative_error is not None
        )
        figure = plot_validation_pressure_error(
            (expected,), direction="bubble", x_axis="temperature"
        )
        assert tuple(figure.data[0].y) == pytest.approx(
            (100.0 * expected.bubble_pressure_relative_error,)
        )
        assert "P_pred−P_exp" in figure.layout.yaxis.title.text

    def test_composition_parity_uses_production_incipient_composition(
        self, validation_records
    ) -> None:
        figure = plot_validation_composition_parity(
            validation_records, direction="bubble", display="mol %"
        )
        assert figure.layout.xaxis.title.text == "Experimental composition (mol %)"
        assert max(figure.data[0].x) <= 100.0
        assert max(figure.data[0].y) <= 100.0

    def test_status_plot_preserves_exact_failure_classifications(
        self, validation_records
    ) -> None:
        figure = plot_validation_status(validation_records, direction="dew")
        labels = set(figure.data[0].x)
        assert "PR_ROOT_DEMONSTRATED_PRODUCTION_UNREACHED" in labels
        assert "NO_PR_ROOT_FOUND_IN_DIAGNOSTIC_SCAN" in labels
        assert any(label.startswith("converged:") for label in labels)

    def test_retrospective_diagnostics_are_explicitly_separate(
        self, validation_records
    ) -> None:
        figure = plot_validation_retrospective_diagnostics(validation_records)
        assert len(figure.data) == 1
        assert figure.data[0].name == (
            "Retrospective nearest PR root (not production prediction)"
        )

    def test_dataframe_adapter_does_not_mutate_frame(self) -> None:
        frame = pd.read_csv(VALIDATION_PATH)
        before = frame.copy(deep=True)
        records = validation_plot_records_from_dataframe(frame)
        pd.testing.assert_frame_equal(frame, before)
        assert len(records) == 40


class TestCriticalityAndCriticalSolverFigures:
    def test_synthetic_contours_receive_correct_unswapped_arrays(self) -> None:
        temperatures = (1.0, 2.0, 3.0)
        pressures = (1.0, 2.0, 3.0)
        lambda_grid = tuple(
            tuple(
                (temperature - 2.0) + 2.0 * (pressure - 2.0)
                for temperature in temperatures
            )
            for pressure in pressures
        )
        cubic_grid = tuple(
            tuple(
                3.0 * (temperature - 2.0) - (pressure - 2.0)
                for temperature in temperatures
            )
            for pressure in pressures
        )
        grid = CriticalityGrid(
            temperatures,
            pressures,
            lambda_grid,
            cubic_grid,
            (("applicable",) * 3,) * 3,
        )
        figure = plot_criticality_map(grid, pressure_unit="Pa")
        assert figure.data[0].name.startswith("lambda_min = 0")
        assert tuple(tuple(row) for row in figure.data[0].z) == lambda_grid
        assert figure.data[1].name.startswith("C = 0")
        assert tuple(tuple(row) for row in figure.data[1].z) == cubic_grid
        assert lambda_grid[1][1] == 0.0 and cubic_grid[1][1] == 0.0

    def test_real_scan_and_critical_marker_share_local_neighborhood(
        self, critical_result
    ) -> None:
        scan = scan_mixture_criticality(
            _ch4_c3(),
            CriticalPointScanSettings(321.0, 322.0, 8.4e6, 8.7e6, 3, 3),
        )
        grid = criticality_grid_from_scan(scan)
        figure = plot_criticality_map(scan, critical_point=critical_result)
        critical = next(
            item for item in figure.data if item.name == "Certified critical point"
        )
        assert min(grid.temperatures_k) < critical.x[0] < max(grid.temperatures_k)
        assert (
            min(grid.pressures_pa) / 1.0e6
            < critical.y[0]
            < max(grid.pressures_pa) / 1.0e6
        )
        assert tuple(tuple(row) for row in figure.data[0].z) == grid.lambda_min
        assert tuple(tuple(row) for row in figure.data[1].z) == grid.cubic_coefficient

    def test_invalid_criticality_shape_and_nonfinite_data_are_rejected(self) -> None:
        bad_shape = CriticalityGrid(
            (1.0, 2.0),
            (1.0, 2.0),
            ((1.0, 2.0),),
            ((1.0, 2.0),),
            (("applicable", "applicable"),),
        )
        with pytest.raises(ValueError, match="shape"):
            plot_criticality_map(bad_shape, pressure_unit="Pa")
        nonfinite = CriticalityGrid(
            (1.0, 2.0),
            (1.0, 2.0),
            ((1.0, float("inf")), (1.0, 2.0)),
            ((1.0, 2.0), (1.0, 2.0)),
            (("applicable", "applicable"),) * 2,
        )
        with pytest.raises(ValueError, match="finite or None"):
            plot_criticality_map(nonfinite, pressure_unit="Pa")

    def test_convergence_uses_log_axis_and_absolute_raw_labels(
        self, critical_result
    ) -> None:
        figure = plot_critical_solver_convergence(critical_result)
        assert figure.layout.yaxis.type == "log"
        assert tuple(trace.name for trace in figure.data) == (
            "Scaled residual norm",
            "|lambda_min|",
            "|C|",
        )
        assert tuple(figure.data[0].y) == tuple(
            item.scaled_residual_norm for item in critical_result.history
        )

    def test_conditioning_is_separate_log_figure(self, critical_result) -> None:
        figure = plot_critical_solver_conditioning(critical_result)
        assert figure.layout.yaxis.type == "log"
        assert tuple(figure.data[0].y) == critical_result.jacobian_condition_history

    def test_solver_path_is_explicitly_not_phase_boundary(
        self, critical_result
    ) -> None:
        figure = plot_critical_solver_path(critical_result)
        assert figure.data[0].name == "Accepted Newton trajectory (not phase boundary)"
        assert tuple(figure.data[0].x)[0] == pytest.approx(320.0)
        assert tuple(figure.data[0].x)[-1] == critical_result.temperature_k
        assert "not a thermodynamic phase boundary" in figure.layout.annotations[0].text
        critical = figure.data[1]
        assert tuple(critical.x) == (critical_result.temperature_k,)

    def test_plotting_does_not_modify_critical_result(self, critical_result) -> None:
        before = deepcopy(critical_result)
        plot_critical_solver_convergence(critical_result)
        plot_critical_solver_path(critical_result)
        assert critical_result == before
