"""Adversarial scientific checks and independent protected-evidence equivalence."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pvt_phase_simulator_validation import (
    METRIC_POLICY,
    Agreement,
    CapabilityUnderTest,
    ComparisonAlignmentError,
    ComparisonKey,
    ComparisonState,
    ComponentAlignmentError,
    DataClass,
    DeclaredTolerance,
    FrozenJsonObject,
    GroupingKey,
    InvariantViolationError,
    LegacyDescriptiveStatistics,
    MetricName,
    MetricState,
    MixedDataClassError,
    NotAssessed,
    ObservationUnit,
    PredictionOutcome,
    PredictionValue,
    Reason,
    ReferenceValue,
    SchemaVersionError,
    SerializationError,
    SolverOutcome,
    ToleranceBinding,
    ToleranceKind,
    Uncertainty,
    UncertaintyAssessment,
    UncertaintyDerivation,
    UncertaintyKind,
    UndefinedMetric,
    ValidationPrediction,
    ValidationQuantity,
    ValidationRecord,
    ValidationStatus,
    ValuePhase,
    VectorReduction,
    aggregate_cross_check_agreement,
    aggregate_experimental_accuracy,
    aggregate_group,
    align_values,
    analyze_sensitivity,
    compare_record,
    decode_scientific_artifact,
    decode_validation_record,
    encode_scientific_artifact,
    encode_validation_record,
    format_metric,
    legacy_descriptive_statistics,
    load_module17_validation_evidence,
    module17_anomaly_subset,
    module17_discrepancies,
    solver_outcome,
)

from .test_validation_core import _case, _prediction, _record

ROOT = Path(__file__).resolve().parents[1]
Q = ValidationQuantity
C = CapabilityUnderTest


def uncertainty(value=1.0, kind=UncertaintyKind.EXPANDED, k=None):
    return Uncertainty(value, kind, k, 95.0, "Synthetic published uncertainty.")


def pressure_record(
    reference=100.0,
    predicted=102.0,
    u=None,
    data_class=DataClass.EXPERIMENTAL_VALIDATION,
):
    case = replace(
        _case(data_class), reference_values=(ReferenceValue(Q.PRESSURE, reference, u),)
    )
    prediction = replace(
        _prediction(), values=(PredictionValue(Q.PRESSURE, predicted),)
    )
    return ValidationRecord(case, prediction)


def pressure_comparison(record=None, **kwargs):
    return compare_record(record or pressure_record(), C.BUBBLE_POINT, **kwargs)


def only_q(case):
    assert len(case.quantity_comparisons) == 1
    return case.quantity_comparisons[0]


def roundtrip(value):
    encoded = encode_scientific_artifact(value)
    decoded = decode_scientific_artifact(encoded)
    assert decoded == value
    assert encode_scientific_artifact(decoded) == encoded
    assert b"NaN" not in encoded and b"Infinity" not in encoded
    return encoded


@pytest.mark.parametrize(
    "kind,k,derive,expected_kind,derivation,denominator",
    [
        (
            UncertaintyKind.EXPANDED,
            2.0,
            False,
            UncertaintyKind.EXPANDED,
            UncertaintyDerivation.PUBLISHED,
            1.0,
        ),
        (
            UncertaintyKind.EXPANDED,
            2.0,
            True,
            UncertaintyKind.EXPANDED,
            UncertaintyDerivation.PUBLISHED,
            1.0,
        ),
        (
            UncertaintyKind.EXPANDED,
            None,
            False,
            UncertaintyKind.EXPANDED,
            UncertaintyDerivation.PUBLISHED,
            1.0,
        ),
        (
            UncertaintyKind.STANDARD,
            2.0,
            False,
            UncertaintyKind.STANDARD,
            UncertaintyDerivation.PUBLISHED,
            1.0,
        ),
        (
            UncertaintyKind.STANDARD,
            2.0,
            True,
            UncertaintyKind.EXPANDED,
            UncertaintyDerivation.EXPANDED_FROM_STANDARD,
            2.0,
        ),
        (
            UncertaintyKind.STANDARD,
            None,
            False,
            UncertaintyKind.STANDARD,
            UncertaintyDerivation.PUBLISHED,
            1.0,
        ),
    ],
)
def test_published_and_derived_uncertainty_are_distinct(
    kind, k, derive, expected_kind, derivation, denominator
):
    case = pressure_comparison(
        pressure_record(u=uncertainty(kind=kind, k=k)), derive_expanded=derive
    )
    a = only_q(case).uncertainty_assessment
    assert isinstance(a, UncertaintyAssessment)
    assert a.applied.kind_used is expected_kind
    assert a.applied.derivation is derivation
    assert a.applied.denominator == denominator
    assert a.applied.coverage_factor == k
    assert a.applied.confidence_level_percent == 95.0
    assert a.applied.scope.value == "REFERENCE_ONLY"
    if expected_kind is UncertaintyKind.EXPANDED:
        assert a.expanded_normalized_residual == 2 / denominator
        assert a.standard_normalized_residual is None
    else:
        assert a.standard_normalized_residual == 2 / denominator
        assert a.expanded_normalized_residual is None
    assert a.agreement is (Agreement.WITHIN if denominator == 2 else Agreement.OUTSIDE)
    assert b'"scope"' in roundtrip(case)


def test_expansion_requires_explicit_k_and_never_infers_from_confidence():
    with pytest.raises(ValueError, match="coverage_factor"):
        pressure_comparison(
            pressure_record(u=uncertainty(kind=UncertaintyKind.STANDARD)),
            derive_expanded=True,
        )


def test_uncertainty_cannot_borrow_across_quantities_specified_conditions_or_phases():
    record = _record()
    composition = record.case.reference_values[1]
    specified = replace(
        composition, phase=ValuePhase.LIQUID, uncertainty=uncertainty((0.025, 0.025))
    )
    case = replace(
        record.case, specified_conditions=(*record.case.specified_conditions, specified)
    )
    result = compare_record(ValidationRecord(case, record.prediction), C.BUBBLE_POINT)
    comp = next(
        q for q in result.quantity_comparisons if q.key.quantity is Q.MOLE_FRACTION
    )
    assert comp.uncertainty_assessment == NotAssessed(Reason.NO_REFERENCE_UNCERTAINTY)
    assert next(
        q for q in result.quantity_comparisons if q.key.quantity is Q.PRESSURE
    ).uncertainty_assessment != NotAssessed(Reason.NO_REFERENCE_UNCERTAINTY)


def vector_record(u=(0.01, 0.02), predicted=(0.79, 0.21), ids=("methane", "ethane")):
    record = _record()
    reference = replace(record.case.reference_values[1], uncertainty=uncertainty(u))
    prediction = PredictionValue(Q.MOLE_FRACTION, predicted, ValuePhase.VAPOR, ids)
    return ValidationRecord(
        replace(record.case, reference_values=(reference,)),
        replace(record.prediction, values=(prediction,)),
    )


def test_vector_permutation_aligns_prediction_and_its_reference_uncertainty():
    original = pressure_comparison(vector_record())
    permuted = pressure_comparison(
        vector_record(predicted=(0.21, 0.79), ids=("ethane", "methane"))
    )
    assert original == permuted
    q = only_q(original)
    a = q.uncertainty_assessment
    assert isinstance(a, UncertaintyAssessment)
    assert a.applied.denominator == (0.01, 0.02)
    assert a.expanded_normalized_residual == tuple(
        e / u for e, u in zip(q.errors.error, (0.01, 0.02), strict=True)
    )
    assert a.criterion.value == "ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY"
    # Permuting the reference also permutes the uncertainty it owns.
    record = vector_record()
    ref = replace(
        record.case.reference_values[0],
        value=(0.2, 0.8),
        component_ids=("ethane", "methane"),
        uncertainty=uncertainty((0.02, 0.01)),
    )
    reversed_q = only_q(
        pressure_comparison(
            ValidationRecord(
                replace(record.case, reference_values=(ref,)), record.prediction
            )
        )
    )
    assert reversed_q.uncertainty_assessment.expanded_normalized_residual == tuple(
        reversed(a.expanded_normalized_residual)
    )
    roundtrip(original)


@pytest.mark.parametrize(
    "u,reason",
    [
        ((0.01, None), Reason.MISSING_COMPONENT_UNCERTAINTY),
        ((None, 0.02), Reason.MISSING_COMPONENT_UNCERTAINTY),
        ((0.01, 0.0), Reason.ZERO_UNCERTAINTY_DENOMINATOR),
    ],
)
def test_vector_requires_every_component_uncertainty(u, reason):
    result = pressure_comparison(vector_record(u=u))
    assert only_q(result).uncertainty_assessment == NotAssessed(reason)
    roundtrip(result)
    record = vector_record(u=u)
    assert encode_validation_record(
        decode_validation_record(encode_validation_record(record))
    ) == encode_validation_record(record)


def test_zero_scalar_uncertainty_is_never_a_residual():
    result = pressure_comparison(pressure_record(u=uncertainty(0.0)))
    assert only_q(result).uncertainty_assessment == NotAssessed(
        Reason.ZERO_UNCERTAINTY_DENOMINATOR
    )
    roundtrip(result)


@pytest.mark.parametrize(
    "reference,reason",
    [
        (0.0, Reason.ZERO_REFERENCE_DENOMINATOR),
        (-1.0, Reason.NEGATIVE_REFERENCE_DENOMINATOR),
    ],
)
def test_invalid_relative_denominators_keep_absolute_metrics(reference, reason):
    case = pressure_comparison(pressure_record(reference=reference))
    assert only_q(case).errors.relative_error == UndefinedMetric(reason)
    aggregate = aggregate_experimental_accuracy((case,)).accuracy_aggregates[0]
    by_name = {m.name: m for m in aggregate.metrics}
    assert by_name[MetricName.MAE].value == abs(102.0 - reference)
    rel = by_name[MetricName.AARD_PERCENT]
    assert (
        rel.state is MetricState.UNDEFINED
        and rel.value is None
        and rel.reason is reason
    )
    assert rel.sample_count == 0 and rel.coverage.compared_cases == 1
    roundtrip(aggregate)


def test_fraction_relative_metrics_and_temperature_relative_policy_are_disabled():
    for quantity in (Q.MOLE_FRACTION, Q.VAPOR_FRACTION, Q.TEMPERATURE):
        assert "relative" not in METRIC_POLICY[quantity].per_observation
        assert MetricName.AARD_PERCENT in METRIC_POLICY[quantity].disabled
    q = only_q(pressure_comparison(vector_record()))
    assert q.errors.relative_error is None


@pytest.mark.parametrize(
    "ids", [("methane", "propane"), ("methane", "methane"), ("methane",)]
)
def test_component_mismatch_duplicate_and_length_raise(ids):
    with pytest.raises(ComponentAlignmentError):
        vector_record(ids=ids)


def test_quantity_phase_and_basis_mismatches_raise():
    with pytest.raises(ComparisonAlignmentError):
        align_values(ReferenceValue(Q.PRESSURE, 1), PredictionValue(Q.TEMPERATURE, 1))
    with pytest.raises(ComparisonAlignmentError):
        align_values(
            ReferenceValue(Q.DENSITY, 1, phase=ValuePhase.LIQUID),
            PredictionValue(Q.DENSITY, 1, ValuePhase.VAPOR),
        )
    for quantity in (Q.MOLE_FRACTION, Q.DENSITY, Q.COMPRESSIBILITY_FACTOR):
        with pytest.raises(ComparisonAlignmentError):
            PredictionValue(quantity, 1)
    for quantity in (Q.PRESSURE, Q.TEMPERATURE, Q.VAPOR_FRACTION):
        with pytest.raises(ComparisonAlignmentError):
            ReferenceValue(quantity, 1, phase=ValuePhase.OVERALL)
    with pytest.raises(ComparisonAlignmentError):
        tolerance(quantity=Q.DENSITY, unit="mol/m^3")


def tolerance(**kwargs):
    return DeclaredTolerance(
        **(
            {
                "quantity": Q.PRESSURE,
                "value": 5.0,
                "unit": "Pa",
                "justification": "Synthetic protocol requirement",
                "source_citation": "Synthetic protocol, section 1",
                "scope": "Synthetic pressure",
                "tolerance_kind": ToleranceKind.ABSOLUTE,
            }
            | kwargs
        )
    )


def test_independent_uncertainty_and_tolerance_coexist_and_roundtrip():
    record = pressure_record(u=uncertainty())
    binding = ToleranceBinding(record.identity, ComparisonKey(Q.PRESSURE), tolerance())
    result = pressure_comparison(record, tolerance_bindings=(binding,))
    q = only_q(result)
    assert q.uncertainty_assessment.agreement is Agreement.OUTSIDE
    assert q.tolerance_assessment.agreement is Agreement.WITHIN
    assert q.tolerance_assessment.tolerance == binding.tolerance
    roundtrip(result)
    roundtrip(binding)
    assert only_q(pressure_comparison(record)).tolerance_assessment == NotAssessed(
        Reason.NO_DECLARED_TOLERANCE
    )
    wrong_dataset = replace(
        binding, identity=replace(record.identity, dataset_version="different")
    )
    assert only_q(
        pressure_comparison(record, tolerance_bindings=(wrong_dataset,))
    ).tolerance_assessment == NotAssessed(Reason.NO_DECLARED_TOLERANCE)
    with pytest.raises(ComparisonAlignmentError):
        replace(binding, key=ComparisonKey(Q.TEMPERATURE))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_citation": ""},
        {"justification": ""},
        {"scope": ""},
        {"tolerance_kind": "wrong"},
        {"tolerance_kind": ToleranceKind.RELATIVE, "unit": "Pa"},
        {
            "tolerance_kind": ToleranceKind.RELATIVE,
            "quantity": Q.MOLE_FRACTION,
            "unit": "1",
        },
        {
            "tolerance_kind": ToleranceKind.RELATIVE,
            "quantity": Q.VAPOR_FRACTION,
            "unit": "1",
        },
        {"value": -1.0},
        {"value": float("nan")},
        {"value": float("inf")},
    ],
)
def test_invalid_tolerances_rejected(kwargs):
    with pytest.raises(ValueError):
        tolerance(**kwargs)


@pytest.mark.parametrize(
    "ref,reason",
    [
        (0.0, Reason.ZERO_REFERENCE_DENOMINATOR),
        (-1.0, Reason.NEGATIVE_REFERENCE_DENOMINATOR),
    ],
)
def test_relative_tolerance_requires_positive_reference(ref, reason):
    record = pressure_record(reference=ref)
    binding = ToleranceBinding(
        record.identity,
        ComparisonKey(Q.PRESSURE),
        tolerance(tolerance_kind=ToleranceKind.RELATIVE, unit="1", value=0.05),
    )
    assert only_q(
        pressure_comparison(record, tolerance_bindings=(binding,))
    ).tolerance_assessment == NotAssessed(reason)


def test_solver_outcomes_are_structured_separate_and_never_guessed_from_prose():
    for raw, expected in [
        ("not_found", SolverOutcome.NOT_FOUND),
        ("inconclusive", SolverOutcome.INCONCLUSIVE),
        (None, SolverOutcome.OTHER_FAILURE),
    ]:
        prediction = ValidationPrediction(
            "case-002",
            PredictionOutcome.FAILURE,
            failure_reason="not_found: this prose must not classify the outcome",
            solver_metadata=FrozenJsonObject(
                {} if raw is None else {"legacy_solver_outcome": raw}
            ),
        )
        record = ValidationRecord(_case(), prediction, ValidationStatus.SOLVER_FAILURE)
        result = pressure_comparison(record)
        assert result.solver_outcome is expected
        assert all(
            q.comparison_state is ComparisonState.PREDICTION_UNAVAILABLE
            for q in result.quantity_comparisons
        )
        roundtrip(result)
    with pytest.raises(InvariantViolationError):
        solver_outcome(
            replace(
                _prediction(),
                solver_metadata=FrozenJsonObject(
                    {"legacy_solver_outcome": "not_found"}
                ),
            )
        )


def test_union_of_keys_and_duplicate_keys_are_explicit():
    record = pressure_record()
    prediction = replace(
        record.prediction, values=(PredictionValue(Q.TEMPERATURE, 200),)
    )
    result = pressure_comparison(ValidationRecord(record.case, prediction))
    assert {q.comparison_state for q in result.quantity_comparisons} == {
        ComparisonState.NOT_PREDICTED,
        ComparisonState.REFERENCE_UNAVAILABLE,
    }
    with pytest.raises(ComparisonAlignmentError):
        pressure_comparison(
            ValidationRecord(
                replace(record.case, reference_values=record.case.reference_values * 2),
                record.prediction,
            )
        )
    with pytest.raises(ComparisonAlignmentError):
        pressure_comparison(
            ValidationRecord(
                record.case,
                replace(record.prediction, values=record.prediction.values * 2),
            )
        )


def test_empty_and_failed_aggregates_keep_explicit_coverage():
    case = pressure_comparison()
    key = GroupingKey(
        case.identity, case.system_id, case.capability, ComparisonKey(Q.PRESSURE)
    )
    empty = aggregate_group((), key, ObservationUnit.PER_CASE_SCALAR)
    assert empty.sample_count == 0
    assert all(
        m.value is None
        and m.reason is Reason.NO_USABLE_OBSERVATIONS
        and m.sample_count == 0
        for m in empty.metrics
    )
    roundtrip(empty)
    failure = ValidationPrediction(
        "case-002", PredictionOutcome.FAILURE, failure_reason="failed"
    )
    failed = pressure_comparison(
        ValidationRecord(
            pressure_record().case, failure, ValidationStatus.SOLVER_FAILURE
        )
    )
    aggregate = aggregate_group((failed,), key, ObservationUnit.PER_CASE_SCALAR)
    assert aggregate.coverage.total_cases == aggregate.coverage.other_failure == 1
    assert aggregate.coverage.compared_cases == aggregate.sample_count == 0
    assert "1 other failures" in format_metric(aggregate.metrics[0])
    with pytest.raises(InvariantViolationError):
        replace(aggregate.coverage, eligible_cases=0)


def test_data_classes_never_mix_and_cross_check_has_no_uncertainty_counts():
    exp = pressure_comparison(pressure_record(u=uncertainty()))
    cross = pressure_comparison(
        pressure_record(u=uncertainty(), data_class=DataClass.NUMERICAL_CROSS_CHECK)
    )
    assert only_q(cross).uncertainty_assessment == NotAssessed(Reason.NOT_EXPERIMENTAL)
    for function in (aggregate_experimental_accuracy, aggregate_cross_check_agreement):
        with pytest.raises(MixedDataClassError):
            function((exp, cross))
    with pytest.raises(MixedDataClassError):
        aggregate_experimental_accuracy((cross,))
    with pytest.raises(MixedDataClassError):
        aggregate_cross_check_agreement((exp,))
    summary = aggregate_cross_check_agreement((cross,))
    assert not hasattr(summary, "accuracy_aggregates")
    assert not hasattr(summary.agreement_aggregates[0], "uncertainty_agreement")
    roundtrip(summary)


def test_uncertainty_groups_never_pool_standard_expanded_or_derived():
    base = pressure_record(u=uncertainty())
    cases = []
    for i, (kind, k, derive) in enumerate(
        [
            (UncertaintyKind.EXPANDED, None, False),
            (UncertaintyKind.STANDARD, None, False),
            (UncertaintyKind.STANDARD, 2.0, True),
            (UncertaintyKind.EXPANDED, 2.0, False),
        ]
    ):
        r = pressure_record(u=uncertainty(kind=kind, k=k))
        r = ValidationRecord(
            replace(r.case, case_id=str(i)), replace(r.prediction, case_id=str(i))
        )
        cases.append(pressure_comparison(r, derive_expanded=derive))
    aggregate = aggregate_experimental_accuracy(cases).accuracy_aggregates[0]
    assert len(aggregate.uncertainty_agreement) == 4
    assert all(g.assessable_count == 1 for g in aggregate.uncertainty_agreement)
    assert base.identity == aggregate.grouping_key.identity
    roundtrip(aggregate)


@pytest.fixture(scope="module")
def adapted():
    return load_module17_validation_evidence(ROOT)


@pytest.fixture(scope="module")
def module_cases(adapted):
    capabilities = {d.identity: d.capability for d in adapted.datasets}
    return tuple(compare_record(r, capabilities[r.identity]) for r in adapted.records)


def test_module17_all_fields_match_protected_summary_exactly(module_cases):
    protected = json.loads(
        (ROOT / "docs/validation/module17_vle_validation_summary.json").read_text()
    )
    summary = aggregate_experimental_accuracy(module_cases)
    assert len(summary.accuracy_aggregates) == 8
    for system in protected["systems"]:
        for direction, capability in [("bubble", C.BUBBLE_POINT), ("dew", C.DEW_POINT)]:
            group = tuple(
                c
                for c in module_cases
                if c.system_id == system["system_id"] and c.capability is capability
            )
            aggregates = {
                a.grouping_key.comparison_key.quantity: a
                for a in summary.accuracy_aggregates
                if a.grouping_key.system_id == system["system_id"]
                and a.grouping_key.capability is capability
            }
            pressure, composition = aggregates[Q.PRESSURE], aggregates[Q.MOLE_FRACTION]
            pm = {m.name: m for m in pressure.metrics}
            cm = {m.name: m for m in composition.metrics}
            pc = pressure.coverage
            lp = legacy_descriptive_statistics(group, pressure)
            lc = legacy_descriptive_statistics(group, composition)
            assert isinstance(lp, LegacyDescriptiveStatistics)
            actual = {
                "source_count": pc.total_cases,
                "success_count": pc.converged,
                "failure_count": pc.not_found + pc.inconclusive + pc.other_failure,
                "pressure_mean_absolute_error_pa": pm[MetricName.MAE].value,
                "pressure_aard_percent": pm[MetricName.AARD_PERCENT].value,
                "pressure_rms_relative_percent": pm[
                    MetricName.RMS_RELATIVE_PERCENT
                ].value,
                "pressure_maximum_absolute_relative_percent": pm[
                    MetricName.MAX_ABS_RELATIVE_PERCENT
                ].value,
                "pressure_bias_percent": pm[MetricName.BIAS_PERCENT].value,
                "composition_mean_absolute_component_error": cm[MetricName.MAE].value,
                "composition_maximum_absolute_component_error": cm[
                    MetricName.MAX_ABS_ERROR
                ].value,
                "pressure_uncertainty_available_count": pc.uncertainty_assessable_count,
                "pressure_within_one_uncertainty_count": pressure.uncertainty_agreement[
                    0
                ].within_count,
                "pressure_within_two_uncertainties_count": (
                    lp.within_two_expanded_uncertainties_count
                ),
                "composition_uncertainty_available_count": (
                    composition.coverage.uncertainty_assessable_count
                )
                if direction == "bubble"
                else None,
                "composition_within_one_uncertainty_count": (
                    composition.uncertainty_agreement[0].within_count
                )
                if direction == "bubble"
                else None,
                "composition_within_two_uncertainties_count": (
                    lc.within_two_expanded_uncertainties_count
                )
                if direction == "bubble"
                else None,
            }
            assert actual == system[f"production_selected_{direction}_metrics"]
            assert composition.sample_count == 2 * pc.compared_cases
            assert pressure.sample_count == pc.compared_cases
            if direction == "dew":
                assert composition.coverage.uncertainty_assessable_count == 0
                assert lc.sample_count == 0
                for case in group:
                    q = next(
                        q
                        for q in case.quantity_comparisons
                        if q.key.quantity is Q.MOLE_FRACTION
                    )
                    if q.comparison_state is ComparisonState.COMPARED:
                        assert q.uncertainty_assessment == NotAssessed(
                            Reason.NO_REFERENCE_UNCERTAINTY
                        )
            discrepancies = module17_discrepancies(group, composition)
            assert [d.identifier for d in discrepancies] == ["LD-1", "LD-2", "LD-3"]
            assert all(d.changes_documented_conclusion is False for d in discrepancies)
            for d in discrepancies:
                roundtrip(d)
            roundtrip(lp)
            with pytest.raises(TypeError):
                aggregate_experimental_accuracy((lp,))
    roundtrip(summary)


def test_module17_coverage_and_observation_units(module_cases):
    expected = {
        ("ch4_c2", C.BUBBLE_POINT): (17, 11, 6, 0),
        ("ch4_c2", C.DEW_POINT): (17, 15, 2, 0),
        ("ch4_c3", C.BUBBLE_POINT): (23, 20, 3, 0),
        ("ch4_c3", C.DEW_POINT): (23, 7, 2, 14),
    }
    per_component = aggregate_experimental_accuracy(module_cases)
    per_case = aggregate_experimental_accuracy(
        module_cases,
        vector_observation_unit=ObservationUnit.PER_CASE_VECTOR,
        reduction=VectorReduction.MEAN_ABS_COMPONENT,
    )
    for a, b in zip(
        per_component.accuracy_aggregates, per_case.accuracy_aggregates, strict=True
    ):
        coverage = a.coverage
        assert (
            coverage.total_cases,
            coverage.converged,
            coverage.not_found,
            coverage.inconclusive,
        ) == expected[(a.grouping_key.system_id, a.grouping_key.capability)]
        assert coverage.other_failure == 0
        assert b.sample_count == coverage.compared_cases
        if a.grouping_key.comparison_key.quantity is Q.MOLE_FRACTION:
            assert a.observation_unit is ObservationUnit.PER_COMPONENT
            assert b.observation_unit is ObservationUnit.PER_CASE_VECTOR
            assert a.sample_count == 2 * b.sample_count
        else:
            assert a == b
    pooled = aggregate_experimental_accuracy(module_cases, pooled_across_systems=True)
    assert len(pooled.accuracy_aggregates) == 12
    assert (
        tuple(
            a
            for a in pooled.accuracy_aggregates
            if not a.grouping_key.pooled_across_systems
        )
        == per_component.accuracy_aggregates
    )


def test_sensitivity_reproduces_every_legacy_field_and_preserves_primary(
    module_cases, adapted
):
    legacy = json.loads(
        (ROOT / "docs/validation/module17_vle_validation_summary.json").read_text()
    )["source_anomaly_sensitivity_283_38_k"]
    subset = module17_anomaly_subset(ROOT)
    before = tuple(encode_validation_record(r) for r in adapted.records)
    with (ROOT / "docs/validation/module17_vle_validation.csv").open(
        newline=""
    ) as stream:
        legacy_ids = {
            row["source_point_id"]
            for row in csv.DictReader(stream)
            if row["system_id"] == "ch4_c3" and float(row["temperature_k"]) == 283.38
        }
    assert set(subset.excluded_case_ids) == {
        f"{identity}::{capability.value.lower()}"
        for identity in legacy_ids
        for capability in (C.BUBBLE_POINT, C.DEW_POINT)
    }
    manifest = json.loads((ROOT / subset.source).read_text())
    assert subset.reason in manifest["source_anomalies"]
    for direction, capability in [("bubble", C.BUBBLE_POINT), ("dew", C.DEW_POINT)]:
        cases = tuple(
            c
            for c in module_cases
            if c.system_id == "ch4_c3" and c.capability is capability
        )
        primary = next(
            a
            for a in aggregate_experimental_accuracy(cases).accuracy_aggregates
            if a.grouping_key.comparison_key.quantity is Q.PRESSURE
        )
        result = analyze_sensitivity(cases, primary, subset)
        assert result.primary is primary
        actual = {
            "included_success_count": primary.coverage.converged,
            "excluded_success_count": result.alternate.coverage.converged,
        }
        for name, metric, shift_prefix in [
            ("aard", MetricName.AARD_PERCENT, "aard"),
            ("bias", MetricName.BIAS_PERCENT, "bias"),
            ("rms_relative", MetricName.RMS_RELATIVE_PERCENT, "rms"),
        ]:
            actual[f"included_{name}_percent"] = next(
                m.value for m in primary.metrics if m.name is metric
            )
            actual[f"excluded_{name}_percent"] = next(
                m.value for m in result.alternate.metrics if m.name is metric
            )
            actual[f"{shift_prefix}_shift_when_excluded_percentage_points"] = next(
                s.value for s in result.shifts if s.metric is metric
            )
        assert actual == legacy[direction]
        roundtrip(result)
    assert tuple(encode_validation_record(r) for r in adapted.records) == before


def test_schema_11_rejection_and_unknown_scientific_enums_do_not_mutate_input():
    record = _record()
    payload = json.loads(encode_validation_record(record))
    payload["schema_version"] = "1.1"
    original = copy.deepcopy(payload)
    with pytest.raises(
        SchemaVersionError,
        match=(
            "phase identity, component identity and per-quantity "
            "assessment semantics would have to be guessed"
        ),
    ):
        decode_validation_record(json.dumps(payload))
    assert payload == original
    encoded = encode_scientific_artifact(pressure_comparison())
    with pytest.raises(SchemaVersionError, match="cannot be converted"):
        decode_scientific_artifact(encoded.replace(b'"1.2"', b'"1.1"'))
    with pytest.raises(ValueError):
        decode_scientific_artifact(encoded.replace(b'"CONVERGED"', b'"FUTURE_OUTCOME"'))
    with pytest.raises(SerializationError):
        decode_scientific_artifact(
            encoded.replace(b"102.0", b"NaN").replace(b"2.0", b"NaN")
        )


def test_protected_artifacts_unchanged():
    expected = {
        "tests/golden_master/baseline.csv": (
            "530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE"
        ),
        "data/component_properties.csv": (
            "C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A"
        ),
        "docs/validation/module17_vle_validation.csv": (
            "B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482"
        ),
        "docs/validation/module17_vle_validation_summary.json": (
            "5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870"
        ),
    }
    for path, digest in expected.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper() == digest


def test_different_phases_and_quantities_cannot_pool():
    record = pressure_record()
    references = (
        ReferenceValue(Q.DENSITY, 500, phase=ValuePhase.LIQUID),
        ReferenceValue(Q.DENSITY, 10, phase=ValuePhase.VAPOR),
        ReferenceValue(Q.PRESSURE, 100),
    )
    predictions = (
        PredictionValue(Q.DENSITY, 505, ValuePhase.LIQUID),
        PredictionValue(Q.DENSITY, 12, ValuePhase.VAPOR),
        PredictionValue(Q.PRESSURE, 103),
    )
    case = pressure_comparison(
        ValidationRecord(
            replace(record.case, reference_values=references),
            replace(record.prediction, values=predictions),
        )
    )
    aggregates = aggregate_experimental_accuracy((case,)).accuracy_aggregates
    assert len(aggregates) == 3
    assert {a.grouping_key.comparison_key for a in aggregates} == {
        ComparisonKey(Q.DENSITY, ValuePhase.LIQUID),
        ComparisonKey(Q.DENSITY, ValuePhase.VAPOR),
        ComparisonKey(Q.PRESSURE),
    }
    assert all(a.sample_count == 1 for a in aggregates)
    roundtrip(aggregate_experimental_accuracy((case,)))


def test_vector_tolerance_requires_every_component_and_is_identity_aligned():
    record = vector_record(predicted=(0.23, 0.77), ids=("ethane", "methane"))
    bound = tolerance(quantity=Q.MOLE_FRACTION, unit="1", value=0.02)
    binding = ToleranceBinding(
        record.identity, ComparisonKey(Q.MOLE_FRACTION, ValuePhase.VAPOR), bound
    )
    result = pressure_comparison(record, tolerance_bindings=(binding,))
    assert only_q(result).tolerance_assessment.agreement is Agreement.OUTSIDE
    larger = replace(binding, tolerance=replace(bound, value=0.04))
    assert (
        only_q(
            pressure_comparison(record, tolerance_bindings=(larger,))
        ).tolerance_assessment.agreement
        is Agreement.WITHIN
    )


def test_exclusion_coverage_keeps_total_but_removes_eligibility():
    base = pressure_record()
    excluded = ValidationRecord(
        base.case,
        base.prediction,
        ValidationStatus.EXCLUDED,
        "Synthetic scope exclusion",
    )
    comparison = pressure_comparison(excluded)
    aggregate = aggregate_experimental_accuracy((comparison,)).accuracy_aggregates[0]
    c = aggregate.coverage
    assert c.total_cases == c.excluded_cases == c.reference_available_cases == 1
    assert (
        c.eligible_cases
        == c.converged
        == c.compared_cases
        == c.metric_observation_count
        == 0
    )
    assert all(m.reason is Reason.NO_USABLE_OBSERVATIONS for m in aggregate.metrics)
    roundtrip(comparison)


def test_summary_constructors_cannot_smuggle_wrong_class_aggregates():
    from pvt_phase_simulator_validation import (
        CrossCheckAgreementSummary,
        ExperimentalAccuracySummary,
    )

    exp = aggregate_experimental_accuracy((pressure_comparison(),)).accuracy_aggregates
    cross = aggregate_cross_check_agreement(
        (
            pressure_comparison(
                pressure_record(data_class=DataClass.NUMERICAL_CROSS_CHECK)
            ),
        )
    ).agreement_aggregates
    with pytest.raises(MixedDataClassError):
        CrossCheckAgreementSummary((), exp)
    with pytest.raises(MixedDataClassError):
        ExperimentalAccuracySummary((), cross)


@pytest.mark.parametrize("quantity", list(Q))
def test_metric_policies_roundtrip(quantity):
    roundtrip(METRIC_POLICY[quantity])


@pytest.mark.parametrize(
    "status",
    [
        "AGREES_WITHIN_UNCERTAINTY",
        "OUTSIDE_UNCERTAINTY",
        "AGREES_WITHIN_DECLARED_TOLERANCE",
        "OUTSIDE_DECLARED_TOLERANCE",
        "REFERENCE_UNAVAILABLE",
    ],
)
def test_retired_record_statuses_cannot_be_constructed_or_decoded(status):
    base = _record()
    with pytest.raises(ValueError):
        ValidationRecord(base.case, base.prediction, status)
    payload = json.loads(encode_validation_record(base))
    payload["validation_record"]["status"] = status
    with pytest.raises(ValueError):
        decode_validation_record(json.dumps(payload))


def test_all_returned_scientific_dataclasses_roundtrip_individually(module_cases):
    from dataclasses import fields, is_dataclass
    from enum import Enum

    def visit(value):
        if is_dataclass(value):
            roundtrip(value)
            for field in fields(value):
                visit(getattr(value, field.name))
        elif isinstance(value, tuple):
            for item in value:
                visit(item)
        elif isinstance(value, Enum):
            roundtrip(value)

    visit(module_cases[0])
    visit(aggregate_experimental_accuracy(module_cases))


def test_module17_dew_specified_vapor_uncertainty_never_reaches_reference_liquid(
    adapted,
):
    dew = next(
        r
        for r in adapted.records
        if r.case.case_id.endswith("::dew_point")
        and r.prediction.outcome is PredictionOutcome.VALUE
    )
    specified = next(
        v for v in dew.case.specified_conditions if v.quantity is Q.MOLE_FRACTION
    )
    reference = next(
        v for v in dew.case.reference_values if v.quantity is Q.MOLE_FRACTION
    )
    assert specified.phase is ValuePhase.VAPOR
    assert specified.uncertainty.value == (0.025, 0.025)
    assert reference.phase is ValuePhase.LIQUID and reference.uncertainty is None
    q = next(
        q
        for q in compare_record(dew, C.DEW_POINT).quantity_comparisons
        if q.key.quantity is Q.MOLE_FRACTION
    )
    assert q.uncertainty_assessment == NotAssessed(Reason.NO_REFERENCE_UNCERTAINTY)
