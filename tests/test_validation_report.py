from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pvt_phase_simulator_validation import (
    CapabilityUnderTest,
    ComparisonKey,
    DataClass,
    FrozenJsonObject,
    GroupingKey,
    MetricName,
    ObservationUnit,
    PredictionOutcome,
    PredictionValue,
    Reason,
    ReferenceValue,
    Uncertainty,
    UncertaintyKind,
    UndefinedMetric,
    ValidationPrediction,
    ValidationQuantity,
    ValidationRecord,
    ValidationStatus,
    aggregate_experimental_accuracy,
    aggregate_group,
    compare_record,
)
from pvt_phase_simulator_validation.module17_adapter import Module17Adaptation
from pvt_phase_simulator_validation.report import (
    EvidenceInconsistencyError,
    UnsupportedDataClassError,
    build_validation_evidence,
    export_case_ledger_csv,
    export_comparisons_csv,
    export_json,
    render_html,
    write_validation_report,
)
from pvt_phase_simulator_validation.report.declarations import (
    DeclarationError,
    load_declaration,
)
from pvt_phase_simulator_validation.report.evidence import (
    AggregateEvidence,
    ProductionCase,
    ProductionEvidence,
    _build_production,
    _model_configuration,
    _package_version,
    _revision,
)
from pvt_phase_simulator_validation.report.exports import _csv_text
from pvt_phase_simulator_validation.report.figures import (
    ReportFigure,
    _composition_parity,
    _pressure_error,
    build_figures,
    figure_html,
)
from pvt_phase_simulator_validation.report.html import (
    _accuracy,
    _safe_link,
    _sensitivity,
    _unavailable,
    _uncertainty,
)
from pvt_phase_simulator_validation.report.membership import (
    ObservationIdentity,
    prove_aggregate_membership,
)

from .test_validation_core import _case, _dataset, _prediction, _record

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def evidence():  # type: ignore[no-untyped-def]
    return build_validation_evidence(
        ROOT,
        run_id="test-run",
        clock=lambda: datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
    )


@pytest.fixture(scope="module")
def report_html(evidence):  # type: ignore[no-untyped-def]
    return render_html(evidence)


def _strict_constant(value: str) -> None:
    raise ValueError(value)


def _mixed_zero_group():  # type: ignore[no-untyped-def]
    comparisons = []
    records = []
    for case_id, reference, predicted in (
        ("case-A", 100.0, 102.0),
        ("case-B", 200.0, 196.0),
        ("case-Z", 0.0, 3.0),
    ):
        case = replace(
            _case(case_id=case_id),
            reference_values=(ReferenceValue(ValidationQuantity.PRESSURE, reference),),
        )
        prediction = replace(
            _prediction(case_id=case_id),
            values=(PredictionValue(ValidationQuantity.PRESSURE, predicted),),
        )
        record = ValidationRecord(case, prediction)
        records.append(record)
        comparisons.append(compare_record(record, CapabilityUnderTest.BUBBLE_POINT))
    key = GroupingKey(
        records[0].identity,
        records[0].case.system_id,
        CapabilityUnderTest.BUBBLE_POINT,
        ComparisonKey(ValidationQuantity.PRESSURE),
    )
    aggregate = aggregate_group(
        tuple(comparisons), key, ObservationUnit.PER_CASE_SCALAR
    )
    return tuple(records), tuple(comparisons), aggregate


def _production_case_from_record(
    record: ValidationRecord,
    capability: CapabilityUnderTest,
) -> ProductionCase:
    comparison = compare_record(record, capability)
    return ProductionCase(
        record.identity.dataset_id,
        record.identity.dataset_version,
        record.data_class,
        capability,
        record.case.case_id,
        record.case.system_id,
        record.case.component_ids,
        record.case.source_reference,
        record.case.specified_conditions,
        record.case.reference_values,
        record.prediction.outcome,
        record.prediction.values,
        record.prediction.failure_reason,
        record.status,
        record.exclusion_reason,
        comparison.solver_outcome,
    )


def test_declaration_is_strict_and_complete(tmp_path: Path) -> None:
    declaration = load_declaration()
    assert declaration.dataset == "module17"
    assert declaration.dataset_role["parameter_fitting"].status == "NOT_USED"
    assert declaration.dataset_role["evaluation"].basis == "DECLARED"
    assert declaration.archive_verification["article_level_consistency"] == "UNRESOLVED"
    assert declaration.uncertainty_source["coverage_factor"] is None

    source = (
        ROOT / "src/pvt_phase_simulator_validation/report/declarations/module17.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    del payload["uncertainty_source"]["method"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DeclarationError, match="missing=.*method"):
        load_declaration(path=broken)

    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["dataset_role"]["held_out_from_development"]["status"] = "USED"
    broken_role = tmp_path / "broken-role.json"
    broken_role.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        DeclarationError, match="frozen dataset-role declaration differs"
    ):
        load_declaration(path=broken_role)


def test_real_module17_evidence_preserves_every_case_and_proves_membership(
    evidence,
) -> None:  # type: ignore[no-untyped-def]
    assert len(evidence.production.cases) == sum(
        len(dataset.cases) for dataset in evidence.datasets
    )
    assert len(evidence.production.comparisons) == len(evidence.production.cases)
    expected_group_keys = {
        GroupingKey(
            case.identity,
            case.system_id,
            case.capability,
            comparison.key,
        )
        for case in evidence.production.comparisons
        for comparison in case.quantity_comparisons
    }
    assert {
        item.aggregate.grouping_key for item in evidence.production.aggregates
    } == expected_group_keys
    assert {
        item.aggregate.grouping_key for item in evidence.production.vector_aggregates
    } == {
        key
        for key in expected_group_keys
        if key.comparison_key.quantity is ValidationQuantity.MOLE_FRACTION
    }
    assert {item.grouping_key for item in evidence.production.pooled_coverage} == {
        GroupingKey(
            key.identity,
            None,
            key.capability,
            key.comparison_key,
            pooled_across_systems=True,
        )
        for key in expected_group_keys
    }
    assert {case.case_id for case in evidence.production.cases} == {
        case.case_id for dataset in evidence.datasets for case in dataset.cases
    }
    for item in (
        *evidence.production.aggregates,
        *evidence.production.vector_aggregates,
    ):
        assert (
            prove_aggregate_membership(evidence.production.comparisons, item.aggregate)
            == item.membership
        )
        for metric, membership in zip(
            item.aggregate.metrics, item.membership.metric_memberships, strict=True
        ):
            assert len(membership.contributors) == metric.sample_count


def test_required_zero_reference_metric_membership_and_csv_reason(evidence) -> None:  # type: ignore[no-untyped-def]
    records, comparisons, aggregate = _mixed_zero_group()
    metrics = {metric.name: metric for metric in aggregate.metrics}
    assert metrics[MetricName.MAE].sample_count == 3
    assert metrics[MetricName.AARD_PERCENT].sample_count == 2
    assert metrics[MetricName.AARD_PERCENT].value == 2.0
    membership = prove_aggregate_membership(comparisons, aggregate)
    by_metric = {
        item.metric: item.contributors for item in membership.metric_memberships
    }
    assert by_metric[MetricName.MAE] == (
        ObservationIdentity("case-A"),
        ObservationIdentity("case-B"),
        ObservationIdentity("case-Z"),
    )
    assert by_metric[MetricName.AARD_PERCENT] == (
        ObservationIdentity("case-A"),
        ObservationIdentity("case-B"),
    )
    zero_comparison = next(item for item in comparisons if item.case_id == "case-Z")
    zero_errors = zero_comparison.quantity_comparisons[0].errors
    assert zero_errors is not None
    assert zero_errors.relative_error == UndefinedMetric(
        Reason.ZERO_REFERENCE_DENOMINATOR
    )
    tampered = {
        MetricName.AARD_PERCENT: (
            *by_metric[MetricName.AARD_PERCENT],
            ObservationIdentity("case-Z"),
        )
    }
    with pytest.raises(EvidenceInconsistencyError):
        prove_aggregate_membership(
            comparisons,
            aggregate,
            declared_metric_contributors=tampered,
        )
    with pytest.raises(EvidenceInconsistencyError):
        prove_aggregate_membership(comparisons[:-1], aggregate)

    production_cases = tuple(
        ProductionCase(
            record.identity.dataset_id,
            record.identity.dataset_version,
            record.data_class,
            CapabilityUnderTest.BUBBLE_POINT,
            record.case.case_id,
            record.case.system_id,
            record.case.component_ids,
            record.case.source_reference,
            record.case.specified_conditions,
            record.case.reference_values,
            record.prediction.outcome,
            record.prediction.values,
            record.prediction.failure_reason,
            record.status,
            record.exclusion_reason,
            comparison.solver_outcome,
        )
        for record, comparison in zip(records, comparisons, strict=True)
    )
    synthetic = ProductionEvidence(
        production_cases,
        comparisons,
        (AggregateEvidence(aggregate, membership),),
        (),
        (),
    )
    csv_text = export_comparisons_csv(replace(evidence, production=synthetic))
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    zero_row = next(row for row in rows if row["case_id"] == "case-Z")
    assert zero_row["relative_error_state"] == "UNDEFINED"
    assert zero_row["relative_error_reason"] == "ZERO_REFERENCE_DENOMINATOR"


def test_json_contract_is_strict_canonical_and_hashes_stable(evidence) -> None:  # type: ignore[no-untyped-def]
    encoded = export_json(evidence)
    assert "NaN" not in encoded and "Infinity" not in encoded
    document = json.loads(encoded, parse_constant=_strict_constant)
    assert set(document) == {
        "format",
        "volatile",
        "report_metadata",
        "dataset",
        "dataset_role",
        "source_provenance",
        "model_configuration",
        "scope",
        "coverage",
        "aggregates",
        "uncertainty_assessments",
        "cases",
        "failures",
        "sensitivity",
        "legacy",
        "diagnostics",
        "reproducibility",
        "content_sha256",
    }
    assert document["format"]["namespace"] == "openphase.validation_evidence"
    assert document["format"]["schema_version"] == "1.0.0"
    pooled = document["coverage"]["pooled_by_capability"]
    assert pooled
    assert all(set(item) == {"grouping_key", "coverage"} for item in pooled)
    assert all("metrics" not in item for item in pooled)
    stable = {
        key: value
        for key, value in document.items()
        if key not in {"volatile", "content_sha256"}
    }
    canonical = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert document["content_sha256"] == hashlib.sha256(canonical).hexdigest()
    changed_volatile = replace(
        evidence,
        volatile=replace(
            evidence.volatile,
            run_id="another-run",
            generated_at_utc=datetime(2030, 1, 1, tzinfo=UTC),
        ),
    )
    changed_document = json.loads(export_json(changed_volatile))
    assert changed_document["content_sha256"] == document["content_sha256"]
    volatile_pattern = re.compile(
        r"<!-- VOLATILE START -->.*?<!-- VOLATILE END -->", re.DOTALL
    )
    assert volatile_pattern.sub(
        "", render_html(changed_volatile)
    ) == volatile_pattern.sub("", render_html(evidence))
    assert export_comparisons_csv(changed_volatile) == export_comparisons_csv(evidence)
    assert export_case_ledger_csv(changed_volatile) == export_case_ledger_csv(evidence)


def test_csv_exports_are_complete_and_parseable(evidence) -> None:  # type: ignore[no-untyped-def]
    comparisons = list(csv.DictReader(io.StringIO(export_comparisons_csv(evidence))))
    ledger = list(csv.DictReader(io.StringIO(export_case_ledger_csv(evidence))))
    expected_comparison_rows = sum(
        len(comparison.component_ids or (None,))
        for case in evidence.production.comparisons
        for comparison in case.quantity_comparisons
    )
    assert len(comparisons) == expected_comparison_rows
    assert len(ledger) == len(evidence.production.cases)
    assert {row["case_id"] for row in ledger} == {
        case.case_id for case in evidence.production.cases
    }
    failures = {
        case.case_id
        for case in evidence.production.cases
        if case.solver_outcome.value != "CONVERGED"
    }
    assert failures <= {row["case_id"] for row in ledger}
    assert all(row["comparison_state"] for row in comparisons)
    for row in comparisons:
        if not row["coverage_factor"]:
            assert row["coverage_factor_state"]
            assert row["coverage_factor_reason"]
        if not row["expanded_normalized_residual"]:
            assert row["expanded_normalized_residual_state"]
            assert row["expanded_normalized_residual_reason"]
        if not row["standard_normalized_residual"]:
            assert row["standard_normalized_residual_state"]
            assert row["standard_normalized_residual_reason"]
        if not row["tolerance_value"]:
            assert row["tolerance_state"]
            assert row["tolerance_reason"]
    assessed = [row for row in comparisons if row["uncertainty_state"] == "ASSESSED"]
    assert assessed
    assert {row["coverage_factor_state"] for row in assessed} == {"NOT_STATED"}
    assert {row["coverage_factor_reason"] for row in assessed} == {
        "NOT_STATED_BY_SOURCE"
    }
    assert {row["expanded_normalized_residual_state"] for row in assessed} == {
        "AVAILABLE"
    }
    assert {row["standard_normalized_residual_state"] for row in assessed} == {
        "NOT_APPLICABLE"
    }
    assert {row["standard_normalized_residual_reason"] for row in assessed} == {
        "KIND_USED_EXPANDED"
    }


def test_csv_residual_states_follow_c_uncertainty_kind(evidence) -> None:  # type: ignore[no-untyped-def]
    case = _case(case_id="case-standard-uncertainty")
    pressure = replace(
        case.reference_values[0],
        uncertainty=Uncertainty(
            1250.0,
            UncertaintyKind.STANDARD,
            None,
            None,
            "Synthetic standard uncertainty.",
        ),
    )
    case = replace(case, reference_values=(pressure, *case.reference_values[1:]))
    record = ValidationRecord(
        case,
        _prediction(case_id="case-standard-uncertainty"),
    )
    comparison = compare_record(record, CapabilityUnderTest.BUBBLE_POINT)
    production = ProductionEvidence(
        (_production_case_from_record(record, CapabilityUnderTest.BUBBLE_POINT),),
        (comparison,),
        (),
        (),
        (),
    )
    rows = list(
        csv.DictReader(
            io.StringIO(
                export_comparisons_csv(replace(evidence, production=production))
            )
        )
    )
    pressure_row = next(row for row in rows if row["quantity"] == "PRESSURE")
    assert pressure_row["standard_normalized_residual_state"] == "AVAILABLE"
    assert pressure_row["standard_normalized_residual_reason"] == ""
    assert pressure_row["expanded_normalized_residual_state"] == "NOT_APPLICABLE"
    assert pressure_row["expanded_normalized_residual_reason"] == "KIND_USED_STANDARD"


def test_html_is_self_contained_scoped_and_responsive(
    evidence, report_html: str
) -> None:  # type: ignore[no-untyped-def]
    required = (
        (
            "The uncertainty comparison uses uncertainty on the "
            "experimental/reference quantity only. It is not a complete propagated "
            "uncertainty budget and does not include specified-condition uncertainty, "
            "EOS-parameter uncertainty, covariance, or model-form uncertainty."
        ),
        "RETROSPECTIVE DIAGNOSTICS — NOT PRODUCTION PREDICTIONS",
        "article-level consistency",
        "UNRESOLVED",
        "not stated by the source",
        "overflow-x:auto",
        "@media(max-width:520px)",
    )
    for phrase in required:
        assert phrase in report_html
    conditions = report_html.split('<section id="conditions"', 1)[1].split(
        "</section>", 1
    )[0]
    assert conditions.count("<tr>") == 5
    assert "methane, ethane" in conditions
    assert "methane, propane" in conditions
    comparison_coverage = report_html.split('<section id="comparison-coverage"', 1)[
        1
    ].split("</section>", 1)[0]
    assert comparison_coverage.count("<table>") == 3
    assert "Reference availability is not a solver outcome." in comparison_coverage
    assert "Uncertainty assessable (of compared)" in comparison_coverage
    assert "blind" not in report_html.casefold()
    assert "held-out" not in report_html.casefold()
    assert not re.search(
        r"<(?:link|img|iframe)\b|<script[^>]+src=",
        report_html,
        flags=re.IGNORECASE,
    )
    assert report_html.count("plotly.js v") == 1

    class StructureParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.sections: list[str | None] = []
            self.scripts: list[dict[str, str | None]] = []

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            attributes = dict(attrs)
            if tag == "section":
                self.sections.append(attributes.get("id"))
            elif tag == "script":
                self.scripts.append(attributes)

    parser = StructureParser()
    parser.feed(report_html)
    assert len(parser.sections) == 21
    assert len(parser.scripts) == 15
    assert all("src" not in script for script in parser.scripts)
    figures = build_figures(evidence.production)
    assert len(figures) == 14
    assert len({item.figure_id for item in figures}) == 14
    assert all(item.figure_id in report_html for item in figures)
    assert 'href="#membership-' in report_html


@pytest.mark.parametrize(
    ("tree_state", "required", "forbidden"),
    (
        ("CLEAN", "tree state: <strong>CLEAN</strong>", 'class="dirty"'),
        (
            "DIRTY",
            "Not reproducible from a commit alone.",
            "Repository tree state is UNKNOWN",
        ),
        (
            "UNKNOWN",
            "Repository tree state is UNKNOWN; cleanliness is not established.",
            "Not reproducible from a commit alone.",
        ),
    ),
)
def test_html_tree_state_banners(
    evidence, tree_state: str, required: str, forbidden: str
) -> None:  # type: ignore[no-untyped-def]
    modified = replace(
        evidence,
        reproducibility=replace(evidence.reproducibility, tree_state=tree_state),
    )
    rendered = render_html(modified)
    assert required in rendered
    assert forbidden not in rendered


def test_diagnostics_are_structurally_isolated(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import pvt_phase_simulator_validation.report.evidence as evidence_module

    sentinel = "</script><script>diagnostic-only-sentinel()</script>"
    adaptation = evidence_module.load_module17_validation_evidence(ROOT)
    record = adaptation.records[0]
    planted = ValidationRecord(
        record.case,
        replace(
            record.prediction,
            diagnostics=(*record.prediction.diagnostics, sentinel),
        ),
        record.status,
        record.exclusion_reason,
    )
    modified_adaptation = replace(
        adaptation,
        records=(planted, *adaptation.records[1:]),
    )
    monkeypatch.setattr(
        evidence_module,
        "load_module17_validation_evidence",
        lambda _root: modified_adaptation,
    )
    modified = build_validation_evidence(ROOT, run_id="diagnostic-sentinel")
    document = json.loads(export_json(modified))
    assert sentinel not in json.dumps(document["cases"])
    assert sentinel in json.dumps(document["diagnostics"])
    assert sentinel not in export_comparisons_csv(modified)
    assert sentinel not in export_case_ledger_csv(modified)
    rendered = render_html(modified)
    assert "diagnostic-only-sentinel()" in rendered
    assert "</script><script>diagnostic-only-sentinel()" not in rendered
    sections = re.findall(
        r'<section id="([^"]+)".*?</section>', rendered, flags=re.DOTALL
    )
    assert "diagnostics" in sections
    for section_id in sections:
        section = rendered.split(f'<section id="{section_id}"', 1)[1].split(
            "</section>", 1
        )[0]
        assert ("diagnostic-only-sentinel()" in section) == (
            section_id == "diagnostics"
        )


def test_other_failure_is_preserved_in_report_exports(evidence) -> None:  # type: ignore[no-untyped-def]
    from pvt_phase_simulator_validation import load_module17_validation_evidence

    adaptation = load_module17_validation_evidence(ROOT)
    original = adaptation.records[0]
    failure = ValidationPrediction(
        original.case.case_id,
        PredictionOutcome.FAILURE,
        failure_reason="synthetic unclassified failure",
        diagnostics=original.prediction.diagnostics,
        solver_metadata=FrozenJsonObject({}),
    )
    failed_record = ValidationRecord(
        original.case,
        failure,
        ValidationStatus.SOLVER_FAILURE,
    )
    modified = replace(
        adaptation,
        records=(failed_record, *adaptation.records[1:]),
    )
    production, _ = _build_production(modified)
    failed_case = next(
        case for case in production.cases if case.case_id == original.case.case_id
    )
    assert failed_case.solver_outcome.value == "OTHER_FAILURE"
    ledger = list(
        csv.DictReader(
            io.StringIO(
                export_case_ledger_csv(replace(evidence, production=production))
            )
        )
    )
    failed_row = next(row for row in ledger if row["case_id"] == failed_case.case_id)
    assert failed_row["solver_outcome"] == "OTHER_FAILURE"
    assert failed_row["failure_reason"] == "synthetic unclassified failure"


def test_reference_unavailable_and_uncertainty_unavailable_are_distinct(
    evidence,
) -> None:  # type: ignore[no-untyped-def]
    compared_record = _record(case_id="case-compared-no-uncertainty")
    missing_reference_record = ValidationRecord(
        replace(
            _case(case_id="case-reference-unavailable"),
            reference_values=(_case().reference_values[0],),
        ),
        _prediction(case_id="case-reference-unavailable"),
    )
    records = (compared_record, missing_reference_record)
    comparisons = tuple(
        compare_record(record, CapabilityUnderTest.BUBBLE_POINT) for record in records
    )
    production = ProductionEvidence(
        tuple(
            _production_case_from_record(record, CapabilityUnderTest.BUBBLE_POINT)
            for record in records
        ),
        comparisons,
        (),
        (),
        (),
    )
    section = _unavailable(replace(evidence, production=production))
    assert "case-reference-unavailable" in section
    assert "REFERENCE_UNAVAILABLE" in section
    assert "case-compared-no-uncertainty" in section
    assert "NO_REFERENCE_UNCERTAINTY" in section


def test_undefined_empty_metric_is_rendered_as_undefined_not_zero(evidence) -> None:  # type: ignore[no-untyped-def]
    records, comparisons, _ = _mixed_zero_group()
    zero_record = records[-1]
    zero_comparison = comparisons[-1]
    key = GroupingKey(
        zero_record.identity,
        zero_record.case.system_id,
        CapabilityUnderTest.BUBBLE_POINT,
        ComparisonKey(ValidationQuantity.PRESSURE),
    )
    aggregate = aggregate_group(
        (zero_comparison,), key, ObservationUnit.PER_CASE_SCALAR
    )
    membership = prove_aggregate_membership((zero_comparison,), aggregate)
    production = ProductionEvidence(
        (_production_case_from_record(zero_record, CapabilityUnderTest.BUBBLE_POINT),),
        (zero_comparison,),
        (AggregateEvidence(aggregate, membership),),
        (),
        (),
    )
    section = _accuracy(replace(evidence, production=production))
    assert "UNDEFINED — ZERO_REFERENCE_DENOMINATOR" in section
    assert "AARD_PERCENT</td><td>0" not in section


def test_sensitivity_keeps_primary_values_and_displays_pressure_units(evidence) -> None:  # type: ignore[no-untyped-def]
    aggregate_by_key = {
        item.aggregate.grouping_key: item.aggregate
        for item in evidence.production.aggregates
    }
    for analysis in evidence.sensitivity:
        assert analysis.primary == aggregate_by_key[analysis.primary.grouping_key]
        assert analysis.primary is not analysis.alternate
    section = _sensitivity(evidence)
    assert (
        "The primary full-dataset result remains authoritative and unchanged."
        in section
    )
    assert "MPa" in section
    assert "Alternate − primary" in section


def test_uncertainty_table_preserves_c_not_assessed_reason(evidence) -> None:  # type: ignore[no-untyped-def]
    section = _uncertainty(evidence)
    assert "NOT ASSESSABLE" in section
    assert "NO_REFERENCE_UNCERTAINTY" in section


def test_composition_parity_uses_comparison_component_identity() -> None:
    case = _case(case_id="case-reversed-reference")
    composition = case.reference_values[1]
    assert isinstance(composition.value, tuple)
    reversed_composition = replace(
        composition,
        value=tuple(reversed(composition.value)),
        component_ids=tuple(reversed(composition.component_ids or ())),
    )
    case = replace(
        case,
        reference_values=(case.reference_values[0], reversed_composition),
    )
    record = ValidationRecord(
        case,
        _prediction(case_id="case-reversed-reference"),
    )
    comparison = compare_record(record, CapabilityUnderTest.BUBBLE_POINT)
    pooled = aggregate_experimental_accuracy(
        (comparison,), pooled_across_systems=True
    ).accuracy_aggregates
    production = ProductionEvidence(
        (_production_case_from_record(record, CapabilityUnderTest.BUBBLE_POINT),),
        (comparison,),
        (),
        (),
        tuple(item for item in pooled if item.grouping_key.pooled_across_systems),
    )
    figure = _composition_parity(production, CapabilityUnderTest.BUBBLE_POINT).figure
    marker_traces = [trace for trace in figure.data if trace.mode == "markers"]
    assert [tuple(trace.x) for trace in marker_traces] == [(0.2,), (0.8,)]


def test_pressure_error_caption_distinguishes_defined_points_from_compared() -> None:
    records, comparisons, _ = _mixed_zero_group()
    pooled = aggregate_experimental_accuracy(
        comparisons, pooled_across_systems=True
    ).accuracy_aggregates
    production = ProductionEvidence(
        tuple(
            _production_case_from_record(record, CapabilityUnderTest.BUBBLE_POINT)
            for record in records
        ),
        comparisons,
        (),
        (),
        tuple(item for item in pooled if item.grouping_key.pooled_across_systems),
    )
    figure = _pressure_error(
        production,
        CapabilityUnderTest.BUBBLE_POINT,
        "F2",
        "temperature",
    )
    assert figure.caption.startswith("2 defined-error points plotted")
    assert "3 compared of 3 total cases" in figure.caption


def test_unsupported_cross_check_is_refused() -> None:
    from pvt_phase_simulator_validation.report.evidence import _validate_data_class

    cross_record = _record(DataClass.NUMERICAL_CROSS_CHECK)
    adaptation = Module17Adaptation((), (cross_record,), FrozenJsonObject({}))  # type: ignore[arg-type]
    with pytest.raises(UnsupportedDataClassError):
        _validate_data_class(adaptation)
    mixed = Module17Adaptation(
        (_dataset(DataClass.EXPERIMENTAL_VALIDATION),),
        (cross_record,),
        FrozenJsonObject({}),
    )
    with pytest.raises(UnsupportedDataClassError):
        _validate_data_class(mixed)


def test_plotly_fragment_neutralizes_hostile_script_text() -> None:
    import plotly.graph_objects as go

    hostile = "</script><script>hostile()</script>"
    figure = go.Figure(go.Scatter(x=[1], y=[2], text=[hostile]))
    fragment = figure_html(
        ReportFigure("hostile-figure", "test", "Hostile", "Test caption", figure)
    )
    assert fragment.count("<script") == 1
    assert fragment.count("</script>") == 1
    assert hostile not in fragment


def test_unknown_repository_and_package_metadata_are_explicit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import pvt_phase_simulator_validation.report.evidence as evidence_module

    def unavailable(*_args):  # type: ignore[no-untyped-def]
        raise OSError("unavailable")

    monkeypatch.setattr(evidence_module, "_git_value", unavailable)
    assert _revision(ROOT) == ("UNKNOWN", "UNKNOWN")

    def missing_package(_name: str) -> str:
        raise evidence_module.PackageNotFoundError

    monkeypatch.setattr(evidence_module, "version", missing_package)
    assert _package_version() == "UNKNOWN"


def test_declared_model_configuration_must_match_engine(tmp_path: Path) -> None:
    source = (
        ROOT / "src/pvt_phase_simulator_validation/report/declarations/module17.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["model_configuration"]["omega_a"] = 123.0
    broken = tmp_path / "model-mismatch.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        EvidenceInconsistencyError,
        match="declared Peng-Robinson constants differ from the engine",
    ):
        _model_configuration(load_declaration(path=broken))


def test_hostile_links_are_never_emitted() -> None:
    assert "href" not in _safe_link("javascript:alert(1)", "<script>")
    assert "&lt;script&gt;" in _safe_link("javascript:alert(1)", "<script>")
    assert "href" not in _safe_link("https://doi.org.evil.invalid/x", "bad", doi=True)
    valid = _safe_link("https://doi.org/10.1/example", 'a "citation"', doi=True)
    assert 'rel="noopener noreferrer"' in valid
    assert "&quot;" in valid
    long_label = "citation <script>" * 400
    long_link = _safe_link(
        "https://doi.org/10.1234/" + "x" * 4000,
        long_label,
        doi=True,
    )
    assert 'href="https://doi.org/10.1234/' in long_link
    assert "<script>" not in long_link
    assert "&lt;script&gt;" in long_link
    assert "href" not in _safe_link(
        "https://doi.org:malformed/10.1/example", "malformed", doi=True
    )


@pytest.mark.parametrize("prefix", ("=", "+", "-", "@", "\t", "\r"))
def test_csv_formula_injection_prefixes_are_neutralized(prefix: str) -> None:
    assert _csv_text(prefix + "payload") == "'" + prefix + "payload"


def test_report_source_has_no_independent_scientific_formula() -> None:
    forbidden_calls = {"abs", "average", "fsum", "mean", "sqrt", "sum"}
    forbidden_operators = (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow)
    for path in sorted(
        (ROOT / "src/pvt_phase_simulator_validation/report").glob("*.py")
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not calls & forbidden_calls
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            if isinstance(node.op, ast.Sub):
                expression = ast.unparse(node)
                assert expression in {"keys - set(value)", "set(value) - keys"}
            elif isinstance(node.op, forbidden_operators):
                expression = ast.unparse(node)
                is_repository_path = isinstance(node.op, ast.Div) and (
                    expression.startswith("Path(")
                    or expression.startswith("directory /")
                )
                assert is_repository_path, expression

    synthetic_formula = ast.parse("result = (prediction - reference) / reference")
    assert any(
        isinstance(node, ast.BinOp) and isinstance(node.op, forbidden_operators)
        for node in ast.walk(synthetic_formula)
    )


def test_f7_caption_counts_converged_cases(evidence) -> None:  # type: ignore[no-untyped-def]
    figures = build_figures(evidence.production)
    f7 = [figure for figure in figures if figure.family == "F7"]
    assert len(f7) == 2
    assert all(" converged of " in figure.caption for figure in f7)
    assert all(" compared of " not in figure.caption for figure in f7)
    composition = [figure for figure in figures if figure.family in {"F5", "F6"}]
    assert len(composition) == 4
    for figure in composition:
        serialized_layout = json.dumps(figure.figure.layout.to_plotly_json()).lower()
        expected_phase = "vapor" if "bubble" in figure.figure_id else "liquid"
        assert expected_phase in serialized_layout


def test_report_import_does_not_load_plotly() -> None:
    script = (
        "import sys; import pvt_phase_simulator_validation.report; "
        "assert not any(name == 'plotly' or name.startswith('plotly.') "
        "for name in sys.modules)"
    )
    subprocess.run(
        (sys.executable, "-c", script),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_protected_paths_remain_unchanged() -> None:
    protected = (
        "src/pvt_phase_simulator",
        "src/pvt_phase_simulator_validation/__init__.py",
        "src/pvt_phase_simulator_validation/_validation.py",
        "src/pvt_phase_simulator_validation/aggregates.py",
        "src/pvt_phase_simulator_validation/aggregation.py",
        "src/pvt_phase_simulator_validation/comparisons.py",
        "src/pvt_phase_simulator_validation/enums.py",
        "src/pvt_phase_simulator_validation/exceptions.py",
        "src/pvt_phase_simulator_validation/hashing.py",
        "src/pvt_phase_simulator_validation/json_values.py",
        "src/pvt_phase_simulator_validation/metrics.py",
        "src/pvt_phase_simulator_validation/models.py",
        "src/pvt_phase_simulator_validation/module17_adapter.py",
        "src/pvt_phase_simulator_validation/module17_legacy.py",
        "src/pvt_phase_simulator_validation/provenance.py",
        "src/pvt_phase_simulator_validation/py.typed",
        "src/pvt_phase_simulator_validation/scientific_serialization.py",
        "src/pvt_phase_simulator_validation/sensitivity.py",
        "src/pvt_phase_simulator_validation/serialization.py",
        "data",
        "docs/validation",
        "docs/EXPERIMENTAL_VALIDATION.md",
        "tests/golden_master",
        "src/pvt_phase_simulator_ui",
        "tools",
        "pyproject.toml",
        "uv.lock",
        ".github",
        "tests/test_validation_core.py",
        "tests/test_validation_metrics.py",
        "tests/test_validation_module17_adapter.py",
        "tests/test_validation_serialization.py",
    )
    worktree = subprocess.run(
        ("git", "status", "--porcelain=v1", "--", *protected),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert worktree.stdout == ""
    history = subprocess.run(
        ("git", "diff", "--name-only", "a772dd6", "--", *protected),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert history.stdout == ""


def test_writer_creates_exactly_four_hash_verified_artifacts(
    evidence, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "module17-report"
    artifacts = write_validation_report(evidence, output)
    assert {path.name for path in output.iterdir()} == {
        "validation_evidence.html",
        "validation_evidence.json",
        "comparisons.csv",
        "case_ledger.csv",
    }
    for artifact in (
        artifacts.html,
        artifacts.json,
        artifacts.comparisons_csv,
        artifacts.case_ledger_csv,
    ):
        assert artifact.sha256 == hashlib.sha256(artifact.path.read_bytes()).hexdigest()
    json.loads(
        artifacts.json.path.read_text(encoding="utf-8"), parse_constant=_strict_constant
    )
    assert len(
        list(
            csv.DictReader(
                artifacts.comparisons_csv.path.open(encoding="utf-8", newline="")
            )
        )
    ) == sum(
        len(comparison.component_ids or (None,))
        for case in evidence.production.comparisons
        for comparison in case.quantity_comparisons
    )
    assert len(
        list(
            csv.DictReader(
                artifacts.case_ledger_csv.path.open(encoding="utf-8", newline="")
            )
        )
    ) == len(evidence.production.cases)
    html_text = artifacts.html.path.read_text(encoding="utf-8")
    document = json.loads(artifacts.json.path.read_text(encoding="utf-8"))
    assert document["content_sha256"] in html_text
    assert artifacts.comparisons_csv.sha256 in html_text
    assert artifacts.case_ledger_csv.sha256 in html_text


def test_output_inside_repository_is_refused(evidence) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="outside the repository"):
        write_validation_report(evidence, ROOT / "build/forbidden-report")
