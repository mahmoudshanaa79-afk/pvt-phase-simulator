# ruff: noqa: E501
"""Self-contained, escaped, responsive professor-facing HTML rendering."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from pvt_phase_simulator_validation.aggregates import MetricResult
from pvt_phase_simulator_validation.comparisons import (
    ComparisonState,
    NotAssessed,
)
from pvt_phase_simulator_validation.enums import ValidationQuantity
from pvt_phase_simulator_validation.json_values import mutable_json
from pvt_phase_simulator_validation.metrics import METRIC_POLICY, MetricState
from pvt_phase_simulator_validation.sensitivity import MetricShift

from .evidence import AggregateEvidence, ProductionCase, ValidationEvidence
from .figures import build_figures, figure_html, plotly_javascript


@dataclass(frozen=True, slots=True)
class _HtmlCell:
    markup: str


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _section(identifier: str, title: str, body: str, class_name: str = "") -> str:
    return f'<section id="{_e(identifier)}" class="{_e(class_name)}"><h2>{_e(title)}</h2>{body}</section>'


def _table(
    headers: tuple[str, ...],
    rows: Sequence[tuple[object, ...]],
    caption: str | None = None,
) -> str:
    caption_html = "" if caption is None else f"<caption>{_e(caption)}</caption>"
    head = "".join(f'<th scope="col">{_e(item)}</th>' for item in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{value.markup if isinstance(value, _HtmlCell) else _e(value)}</td>"
            for value in row
        )
        + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table>{caption_html}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _safe_link(url: str, label: str, *, doi: bool = False) -> str:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and not any(character.isspace() for character in url)
        )
        if doi:
            valid = valid and parsed.hostname == "doi.org"
    except ValueError:
        valid = False
    if not valid:
        return _e(label)
    return f'<a href="{_e(url)}" rel="noopener noreferrer">{_e(label)}</a>'


def _slug(item: AggregateEvidence) -> str:
    key = item.aggregate.grouping_key
    phase = (
        "none" if key.comparison_key.phase is None else key.comparison_key.phase.value
    )
    reduction = (
        "none" if item.aggregate.reduction is None else item.aggregate.reduction.value
    )
    raw = "-".join(
        (
            key.identity.dataset_id,
            str(key.system_id),
            key.capability.value,
            key.comparison_key.quantity.value,
            phase,
            item.aggregate.observation_unit.value,
            reduction,
        )
    )
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")


def _number_with_unit(value: float, unit: str) -> str:
    if unit == "Pa":
        from pvt_phase_simulator.plotting import PressureUnit, convert_pressure

        value = float(convert_pressure(value, PressureUnit.MPA))
        return f"{value:.6g} MPa"
    if unit == "%":
        return f"{value:.6g} %"
    return f"{value:.6g} {unit}"


def _metric_value(metric: MetricResult) -> str:
    if metric.state is MetricState.UNDEFINED:
        assert metric.reason is not None
        return f"UNDEFINED — {metric.reason.value}"
    assert metric.value is not None
    return _number_with_unit(metric.value, metric.unit)


def _shift_value(shift: MetricShift, unit: str) -> str:
    if shift.value is None:
        assert shift.reason is not None
        return f"UNDEFINED — {shift.reason.value}"
    return _number_with_unit(shift.value, unit)


def _summary(evidence: ValidationEvidence) -> str:
    rows = []
    for aggregate in evidence.production.pooled_coverage:
        if (
            aggregate.grouping_key.comparison_key.quantity
            is not ValidationQuantity.PRESSURE
        ):
            continue
        coverage = aggregate.coverage
        rows.append(
            (
                aggregate.grouping_key.capability.value,
                coverage.converged,
                coverage.total_cases,
                coverage.not_found,
                coverage.inconclusive,
                coverage.other_failure,
            )
        )
    primary_rows = []
    for item in evidence.production.aggregates:
        policy = METRIC_POLICY[item.aggregate.grouping_key.comparison_key.quantity]
        for metric in item.aggregate.metrics:
            if metric.name not in policy.primary:
                continue
            key = item.aggregate.grouping_key
            primary_rows.append(
                (
                    key.system_id,
                    key.capability.value,
                    key.comparison_key.quantity.value,
                    metric.name.value,
                    _metric_value(metric),
                    f"{metric.sample_count} observations; {metric.coverage.compared_cases} compared of {metric.coverage.total_cases}",
                )
            )
    role_line = (
        "No model parameters were fitted to this dataset. Repository evidence does not "
        "establish whether it was held out from solver development."
    )
    return (
        '<p class="lede">A traceable account of experimental comparisons, solver coverage, '
        "uncertainty context, and reproducibility. It deliberately assigns no overall score or "
        "scientific acceptance badge.</p>"
        + f'<p class="role-line">{_e(role_line)}</p>'
        + _table(
            (
                "Capability",
                "Converged",
                "Total",
                "Not found",
                "Inconclusive",
                "Other failure",
            ),
            rows,
            "Capability-level solver coverage from C; pooled accuracy is not displayed.",
        )
        + _table(
            (
                "System",
                "Capability",
                "Quantity",
                "Primary metric",
                "Value",
                "Evidence base",
            ),
            primary_rows,
            "Primary metrics are selected by C's metric policy; all enabled metrics appear below.",
        )
    )


def _anomaly_callout(evidence: ValidationEvidence) -> str:
    archive = evidence.declaration.archive_verification
    return (
        '<aside class="callout warning"><h3>Source anomaly — 283.38 K state retained</h3>'
        f"<p>{_e(evidence.sensitivity_subset.reason)}</p>"
        "<p>The ThermoML archive contains this state in paired pressure dataset "
        f"{_e(archive['pressure_dataset_number'])} and vapor dataset {_e(archive['vapor_dataset_number'])}; "
        "the raw SHA-256 equals the manifest and the extractor reproduces the normalized CSV. "
        f"Article table check: {_e(archive['article_table_check'])}. article-level consistency: "
        f"<strong>{_e(archive['article_level_consistency'])}</strong>.</p></aside>"
    )


def _scope(evidence: ValidationEvidence) -> str:
    rows = []
    groups = sorted(
        {(case.system_id, case.capability) for case in evidence.production.cases},
        key=lambda item: (item[0], item[1].value),
    )
    for system_id, capability in groups:
        cases = [
            case
            for case in evidence.production.cases
            if case.system_id == system_id and case.capability is capability
        ]
        temperatures = [_temperature(case) for case in cases]
        pressures = [_reference_pressure(case) for case in cases]
        fractions = [_specified_methane(case)[0] for case in cases]
        phase = _specified_methane(cases[0])[1]
        rows.append(
            (
                system_id,
                capability.value,
                len(cases),
                f"{min(temperatures):.6g}–{max(temperatures):.6g} K",
                f"{_number_with_unit(min(pressures), 'Pa')}–{_number_with_unit(max(pressures), 'Pa')}",
                f"{min(fractions):.6g}–{max(fractions):.6g} ({phase.lower()})",
            )
        )
    return _table(
        (
            "System",
            "Capability",
            "Cases",
            "Specified T",
            "Reference P",
            "Specified CH₄ fraction",
        ),
        rows,
        "All source cases define the scope; difficult and non-converged cases are not removed.",
    ) + _anomaly_callout(evidence)


def _dataset_role(evidence: ValidationEvidence) -> str:
    labels = {
        "parameter_fitting": "Parameter fitting",
        "solver_development": "Solver development",
        "regression_testing": "Regression testing",
        "evaluation": "Evaluation",
        "held_out_from_development": "Development separation",
    }
    rows = [
        (labels[name], role.status, role.basis, "; ".join(role.evidence))
        for name, role in sorted(evidence.declaration.dataset_role.items())
    ]
    return _table(("Role", "Status", "Basis", "Evidence pointer"), rows)


def _temperature(case: ProductionCase) -> float:
    value = next(
        item.value
        for item in case.specified_conditions
        if item.quantity is ValidationQuantity.TEMPERATURE
    )
    assert isinstance(value, float)
    return value


def _reference_pressure(case: ProductionCase) -> float:
    value = next(
        item.value
        for item in case.reference_values
        if item.quantity is ValidationQuantity.PRESSURE
    )
    assert isinstance(value, float)
    return value


def _specified_methane(case: ProductionCase) -> tuple[float, str]:
    value = next(
        item
        for item in case.specified_conditions
        if item.quantity is ValidationQuantity.MOLE_FRACTION
    )
    assert isinstance(value.value, tuple) and value.phase is not None
    by_id = dict(zip(value.component_ids or (), value.value, strict=True))
    return by_id["methane"], value.phase.value


def _conditions(evidence: ValidationEvidence) -> str:
    rows: list[tuple[object, ...]] = []
    samples: dict[tuple[str, str, str], ProductionCase] = {}
    for case in evidence.production.cases:
        samples.setdefault(
            (case.dataset_id, case.system_id, case.capability.value), case
        )
    for sample in (samples[key] for key in sorted(samples)):
        rows.append(
            (
                sample.dataset_id,
                sample.system_id,
                sample.capability.value,
                ", ".join(
                    item.quantity.value
                    + ("" if item.phase is None else f" ({item.phase.value})")
                    for item in sample.specified_conditions
                ),
                ", ".join(
                    item.quantity.value
                    + ("" if item.phase is None else f" ({item.phase.value})")
                    for item in sample.reference_values
                ),
                ", ".join(sample.component_ids),
            )
        )
    return _table(
        (
            "Dataset",
            "System",
            "Capability",
            "Specified quantities",
            "Reference quantities",
            "Component order",
        ),
        rows,
    )


def _solver_coverage(evidence: ValidationEvidence) -> str:
    rows = []
    for item in evidence.production.aggregates:
        if (
            item.aggregate.grouping_key.comparison_key.quantity
            is not ValidationQuantity.PRESSURE
        ):
            continue
        key, coverage = item.aggregate.grouping_key, item.aggregate.coverage
        rows.append(
            (
                key.system_id,
                key.capability.value,
                coverage.total_cases,
                coverage.excluded_cases,
                coverage.eligible_cases,
                coverage.converged,
                coverage.not_found,
                coverage.inconclusive,
                coverage.other_failure,
            )
        )
    note = (
        "<p><strong>NOT_FOUND</strong> means the configured numerical search did not find an "
        "acceptable solution. It does not prove that no physical solution exists.</p>"
    )
    return note + _table(
        (
            "System",
            "Capability",
            "Total",
            "Excluded",
            "Eligible",
            "Converged",
            "Not found",
            "Inconclusive",
            "Other failure",
        ),
        rows,
    )


def _failures(evidence: ValidationEvidence) -> str:
    rows = [
        (
            case.case_id,
            case.system_id,
            case.capability.value,
            case.solver_outcome.value,
            case.failure_reason,
        )
        for case in evidence.production.cases
        if case.solver_outcome.value != "CONVERGED"
    ]
    return _table(
        ("Case", "System", "Capability", "Outcome", "Reason (verbatim)"),
        rows,
        "Every non-converged case remains visible.",
    )


def _comparison_coverage(evidence: ValidationEvidence) -> str:
    reference_rows = []
    uncertainty_rows = []
    state_rows = []
    for item in evidence.production.aggregates:
        aggregate = item.aggregate
        key, coverage = aggregate.grouping_key, aggregate.coverage
        reference_rows.append(
            (
                key.system_id,
                key.capability.value,
                key.comparison_key.quantity.value,
                f"{coverage.reference_available_cases} of {coverage.total_cases}",
            )
        )
        uncertainty_rows.append(
            (
                key.system_id,
                key.capability.value,
                key.comparison_key.quantity.value,
                coverage.compared_cases,
                coverage.metric_observation_count,
                coverage.uncertainty_assessable_count,
            )
        )
        cases = [
            case
            for case in evidence.production.comparisons
            if case.case_id in item.membership.case_ids
        ]
        states = Counter(
            comparison.comparison_state.value
            for case in cases
            for comparison in case.quantity_comparisons
            if comparison.key == key.comparison_key
        )
        state_rows.append(
            (
                key.system_id,
                key.capability.value,
                key.comparison_key.quantity.value,
                *(states.get(state.value, 0) for state in ComparisonState),
            )
        )
    return (
        _table(
            (
                "System",
                "Capability",
                "Quantity",
                "Reference available (of total)",
            ),
            reference_rows,
            "Reference availability is not a solver outcome.",
        )
        + _table(
            (
                "System",
                "Capability",
                "Quantity",
                *(state.value for state in ComparisonState),
            ),
            state_rows,
            "Comparison states are separate from solver outcomes and uncertainty assessability.",
        )
        + _table(
            (
                "System",
                "Capability",
                "Quantity",
                "Compared cases",
                "Metric observations",
                "Uncertainty assessable (of compared)",
            ),
            uncertainty_rows,
            "Uncertainty assessability uses C's reference-only assessment counts.",
        )
    )


def _accuracy(evidence: ValidationEvidence) -> str:
    rows: list[tuple[object, ...]] = []
    membership_blocks = []
    all_items = (
        *evidence.production.aggregates,
        *evidence.production.vector_aggregates,
    )
    for item in all_items:
        aggregate = item.aggregate
        key = aggregate.grouping_key
        aggregate_slug = _slug(item)
        for metric, membership in zip(
            aggregate.metrics, item.membership.metric_memberships, strict=True
        ):
            anchor = f"membership-{aggregate_slug}-{metric.name.value.lower()}"
            rows.append(
                (
                    key.identity.dataset_id,
                    key.system_id,
                    key.capability.value,
                    key.comparison_key.quantity.value,
                    "—"
                    if key.comparison_key.phase is None
                    else key.comparison_key.phase.value,
                    metric.name.value,
                    _metric_value(metric),
                    aggregate.observation_unit.value,
                    "—" if aggregate.reduction is None else aggregate.reduction.value,
                    metric.sample_count,
                    metric.coverage.compared_cases,
                    metric.coverage.total_cases,
                    _HtmlCell(
                        f'<a href="#{_e(anchor)}">{metric.sample_count} contributors</a>'
                    ),
                )
            )
            identities = (
                ", ".join(
                    contributor.case_id
                    + (
                        ""
                        if contributor.component_id is None
                        else f" [{contributor.component_id}]"
                    )
                    for contributor in membership.contributors
                )
                or "No contributors"
            )
            membership_blocks.append(
                f'<details id="{_e(anchor)}"><summary>{_e(key.system_id)} · {_e(key.capability.value)} · {_e(metric.name.value)} — {_e(metric.sample_count)} contributors</summary><p>{_e(identities)}</p></details>'
            )
    table = _table(
        (
            "Dataset",
            "System",
            "Capability",
            "Quantity",
            "Phase",
            "Metric",
            "Value",
            "Observation unit",
            "Reduction",
            "N",
            "Compared",
            "Total",
            "Membership",
        ),
        rows,
        "Enabled C metrics only. PER_COMPONENT and PER_CASE_VECTOR / MEAN_ABS_COMPONENT are distinct statistics.",
    )
    return (
        _anomaly_callout(evidence)
        + table
        + '<div class="memberships"><h3>Proven metric membership</h3>'
        + "".join(membership_blocks)
        + "</div>"
    )


def _uncertainty(evidence: ValidationEvidence) -> str:
    wording = (
        "The uncertainty comparison uses uncertainty on the experimental/reference quantity only. "
        "It is not a complete propagated uncertainty budget and does not include specified-condition "
        "uncertainty, EOS-parameter uncertainty, covariance, or model-form uncertainty."
    )
    source = evidence.declaration.uncertainty_source
    rows: list[tuple[object, ...]] = []
    for item in evidence.production.aggregates:
        key = item.aggregate.grouping_key
        if not item.aggregate.uncertainty_agreement:
            reasons = sorted(
                {
                    comparison.uncertainty_assessment.reason.value
                    for case in evidence.production.comparisons
                    if case.case_id in item.membership.case_ids
                    for comparison in case.quantity_comparisons
                    if comparison.key == key.comparison_key
                    and isinstance(comparison.uncertainty_assessment, NotAssessed)
                }
            )
            rows.append(
                (
                    key.system_id,
                    key.capability.value,
                    key.comparison_key.quantity.value,
                    "NOT ASSESSABLE",
                    "; ".join(reasons) or "NOT_ASSESSED",
                    "—",
                    "—",
                    "—",
                    0,
                    0,
                    0,
                )
            )
        for group in item.aggregate.uncertainty_agreement:
            rows.append(
                (
                    key.system_id,
                    key.capability.value,
                    key.comparison_key.quantity.value,
                    group.kind_used.value,
                    "—",
                    group.derivation.value,
                    "not stated by the source"
                    if group.coverage_factor is None
                    else group.coverage_factor,
                    "not recorded"
                    if group.confidence_level_percent is None
                    else f"{group.confidence_level_percent:g} % (as recorded)",
                    group.assessable_count,
                    group.within_count,
                    group.outside_count,
                )
            )
    return (
        f'<p class="limitation"><strong>{_e(wording)}</strong></p>'
        f"<p>Source record: {_e(source['description'])}; evaluator: {_e(source['evaluator'])}; method: {_e(source['method'])}. "
        f"Coverage factor: <strong>not stated by the source</strong>. {_e(source['manifest_metadata_gap'])}</p>"
        "<p>Vector criterion: <code>ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY</code>; every required component is checked individually against its reference-uncertainty bound.</p>"
        + _table(
            (
                "System",
                "Capability",
                "Quantity",
                "Kind",
                "Reason",
                "Derivation",
                "Coverage factor",
                "Confidence",
                "Assessable",
                "Within",
                "Outside",
            ),
            rows,
        )
    )


def _figures(evidence: ValidationEvidence) -> str:
    cards = []
    for item in build_figures(evidence.production):
        cards.append(
            f'<article class="figure-card"><h3>{_e(item.family)} · {_e(item.title)}</h3>{figure_html(item)}<p class="caption">{_e(item.caption)}</p></article>'
        )
    return "".join(cards)


def _worst_cases(evidence: ValidationEvidence) -> str:
    rows: list[tuple[object, ...]] = []
    for item in evidence.production.aggregates:
        key = item.aggregate.grouping_key
        ranked: list[tuple[float, str, str | None]] = []
        for case in evidence.production.comparisons:
            if case.case_id not in item.membership.case_ids:
                continue
            comparison = next(
                value
                for value in case.quantity_comparisons
                if value.key == key.comparison_key
            )
            if comparison.comparison_state is not ComparisonState.COMPARED:
                continue
            assert comparison.errors is not None
            if key.comparison_key.quantity is ValidationQuantity.PRESSURE:
                value = comparison.errors.absolute_relative_error
                if isinstance(value, float):
                    ranked.append((value, case.case_id, None))
            elif key.comparison_key.quantity is ValidationQuantity.MOLE_FRACTION:
                value = comparison.errors.absolute_error
                assert isinstance(value, tuple)
                ranked.extend(
                    (error, case.case_id, component)
                    for error, component in zip(
                        value, comparison.component_ids or (), strict=True
                    )
                )
        ranked.sort(
            key=lambda entry: (
                -entry[0],
                entry[1],
                "" if entry[2] is None else entry[2],
            )
        )
        metric_label = (
            "C absolute_relative_error"
            if key.comparison_key.quantity is ValidationQuantity.PRESSURE
            else "C per-component absolute_error"
        )
        for rank, (value, case_id, component) in enumerate(ranked[:5], start=1):
            display = (
                f"{value:.3%}"
                if key.comparison_key.quantity is ValidationQuantity.PRESSURE
                else f"{value:.6g}"
            )
            rows.append(
                (
                    key.system_id,
                    key.capability.value,
                    key.comparison_key.quantity.value,
                    rank,
                    case_id,
                    "—" if component is None else component,
                    metric_label,
                    display,
                )
            )
    return _table(
        (
            "System",
            "Capability",
            "Quantity",
            "Rank",
            "Case",
            "Component",
            "Ranking value",
            "Magnitude",
        ),
        rows,
        "Top five COMPARED observations per GroupingKey. Ties break by case ID then component ID; unavailable predictions are never ranked.",
    )


def _unavailable(evidence: ValidationEvidence) -> str:
    rows: list[tuple[object, ...]] = []
    for case in evidence.production.comparisons:
        for comparison in case.quantity_comparisons:
            uncertainty = comparison.uncertainty_assessment
            if (
                comparison.comparison_state is not ComparisonState.COMPARED
                or isinstance(uncertainty, NotAssessed)
            ):
                rows.append(
                    (
                        case.case_id,
                        case.system_id,
                        case.capability.value,
                        comparison.key.quantity.value,
                        comparison.comparison_state.value,
                        "—"
                        if not isinstance(uncertainty, NotAssessed)
                        else uncertainty.reason.value,
                    )
                )
    return _table(
        (
            "Case",
            "System",
            "Capability",
            "Quantity",
            "Comparison state",
            "Uncertainty reason",
        ),
        rows,
        "Reference/prediction unavailability and uncertainty non-assessability remain distinct.",
    )


def _sensitivity(evidence: ValidationEvidence) -> str:
    rows = []
    for analysis in evidence.sensitivity:
        for primary, alternate, shift in zip(
            analysis.primary.metrics,
            analysis.alternate.metrics,
            analysis.shifts,
            strict=True,
        ):
            rows.append(
                (
                    analysis.primary.grouping_key.capability.value,
                    primary.name.value,
                    _metric_value(primary),
                    primary.sample_count,
                    _metric_value(alternate),
                    alternate.sample_count,
                    _shift_value(shift, primary.unit),
                )
            )
    return (
        f"<p>Alternate subset <code>{_e(evidence.sensitivity_subset.subset_id)}</code> excludes only {_e(', '.join(evidence.sensitivity_subset.excluded_case_ids))} by stable identity. The primary full-dataset result remains authoritative and unchanged.</p>"
        f"<p>Reason: {_e(evidence.sensitivity_subset.reason)} Source: <code>{_e(evidence.sensitivity_subset.source)}</code>.</p>"
        + _table(
            (
                "Capability",
                "Metric",
                "Primary",
                "Primary N",
                "Alternate",
                "Alternate N",
                "Alternate − primary",
            ),
            rows,
        )
    )


def _legacy(evidence: ValidationEvidence) -> str:
    count_rows = [
        (
            item.grouping_key.system_id,
            item.grouping_key.capability.value,
            item.grouping_key.comparison_key.quantity.value,
            item.sample_count,
            item.within_two_expanded_uncertainties_count,
            item.label,
        )
        for item in evidence.legacy.descriptive_statistics
    ]
    discrepancy_rows = [
        (
            item.identifier,
            item.metric,
            item.legacy_definition,
            item.new_definition,
            item.cause,
            item.scientific_assessment,
            item.changes_documented_conclusion,
        )
        for item in evidence.legacy.discrepancies
    ]
    return (
        "<p><strong>These historical 2U counts are descriptive evidence only. They are not modern uncertainty agreement and are kept separate from all production uncertainty tables.</strong></p>"
        + _table(
            (
                "System",
                "Capability",
                "Quantity",
                "Assessable",
                "Within historical 2U",
                "Label",
            ),
            count_rows,
        )
        + _table(
            (
                "ID",
                "Metric",
                "Legacy definition",
                "Modern definition",
                "Cause",
                "Assessment",
                "Changes documented conclusion",
            ),
            discrepancy_rows,
        )
    )


def _diagnostics(evidence: ValidationEvidence) -> str:
    interpretation = "".join(
        f"<li><strong>{_e(key)}</strong>: {_e(value)}</li>"
        for key, value in sorted(evidence.diagnostics.interpretation.items())
    )
    cases = []
    for item in evidence.diagnostics.cases:
        payload = json.dumps(
            [mutable_json(value) for value in item.diagnostics],
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        cases.append(
            f"<details><summary>{_e(item.case_id)} · {_e(item.capability.value)}</summary><pre>{_e(payload)}</pre></details>"
        )
    return f"<ul>{interpretation}</ul>" + "".join(cases)


def _model_configuration(evidence: ValidationEvidence) -> str:
    model = evidence.model_configuration
    rows = [
        (
            item.component_id,
            item.critical_temperature_k,
            item.critical_pressure_pa,
            item.acentric_factor,
            item.kappa,
            "Yang & Richter (2025); property-level provenance retained",
        )
        for item in model.components
    ]
    historical = "Generating revision not embedded in the stored prediction artifact. Current code inspection is not proof of the historical generating configuration."
    return (
        f"<p>Declared/verified model: {_e(model.eos)}; Ωa = {_e(model.omega_a)}; Ωb = {_e(model.omega_b)}; κ(ω) = <code>{_e(model.kappa_expression)}</code>; mixing rule: {_e(model.mixing_rule)}; binary-interaction policy: <code>{_e(model.binary_interaction_policy)}</code>.</p>"
        f"<p>Stored prediction artifact introduced at <code>{_e(model.prediction_artifact_introduced_revision)}</code>. <strong>{_e(historical)}</strong></p>"
        + _table(("Component", "Tc (K)", "Pc (Pa)", "ω", "κ", "Property source"), rows)
    )


def _provenance(evidence: ValidationEvidence) -> str:
    manifest = evidence.datasets[0].source_manifest
    doi = (
        ""
        if manifest.doi is None
        else _safe_link(f"https://doi.org/{manifest.doi}", manifest.doi, doi=True)
    )
    archive = _safe_link(manifest.archive_url, manifest.archive_name)
    identities = _table(
        ("Component", "Name", "Formula", "InChIKey", "CAS"),
        [
            (item.component_id, item.name, item.formula, item.inchikey, item.cas)
            for item in manifest.compound_identities
        ],
    )
    return (
        f"<p>{_e(manifest.citation_text)}</p><p>DOI: {doi}<br>Archive: {archive}<br>Access date: {_e(manifest.access_date.isoformat())}</p>"
        f"<p>Raw SHA-256: <code>{_e(manifest.raw_sha256)}</code><br>Normalized SHA-256: <code>{_e(manifest.normalized_sha256)}</code></p>"
        f"<p>Measurement methods: {_e('; '.join(manifest.measurement_methods))}. Conversion: {_e('; '.join(item.expression for item in manifest.unit_conversions))}.</p>"
        f"<p>{_e(manifest.raw_snapshot_policy)}</p>{identities}"
    )


def _limitations() -> str:
    return (
        "<ul><li>Experimental-reference uncertainty alone is assessed; input, parameter, covariance, and model-form contributions are outside scope.</li>"
        "<li>WITHIN does not establish model adequacy; OUTSIDE does not establish disagreement beyond a complete combined uncertainty budget.</li>"
        "<li>Non-convergence is a numerical outcome, not proof that no physical solution exists.</li>"
        "<li>The report describes stored production predictions and does not refit parameters or investigate alternate dew branches.</li></ul>"
    )


def _software_verification(evidence: ValidationEvidence) -> str:
    return (
        "<p>This report does not run or claim test counts. Verification remains in the repository and CI evidence:</p><ul>"
        + "".join(
            f"<li><code>{_e(pointer)}</code></li>"
            for pointer in evidence.declaration.software_verification_pointers
        )
        + "</ul>"
    )


def _reproducibility(evidence: ValidationEvidence) -> str:
    repro = evidence.reproducibility
    pins = _table(
        ("Dataset", "Version", "Raw SHA-256", "Normalized SHA-256"),
        [
            (
                item.identity.dataset_id,
                item.identity.dataset_version,
                item.raw_sha256,
                item.normalized_sha256,
            )
            for item in repro.dataset_pins
        ],
    )
    return (
        f"<p>Comparison/report revision: <code>{_e(repro.git_commit_sha)}</code>; tree state: <strong>{_e(repro.tree_state)}</strong>.</p>"
        f"<p>Stored prediction revision: not embedded; artifact introduced at <code>{_e(evidence.model_configuration.prediction_artifact_introduced_revision)}</code>.</p>"
        f"<p>Report schema: {_e(evidence.schema_version)}; framework schema: {_e(repro.framework_schema_version)}; package: {_e(repro.package_version)}; Python: {_e(repro.python_version)}; platform: {_e(repro.platform)}.</p>"
        f"<p>Reproduce: <code>{_e(repro.reproduction_command)}</code></p>{pins}"
    )


def _inventory(evidence: ValidationEvidence) -> str:
    from .exports import export_case_ledger_csv, export_comparisons_csv, export_json

    json_text = export_json(evidence)
    json_document = json.loads(json_text)
    content_sha256 = json_document["content_sha256"]
    if not isinstance(content_sha256, str):
        raise ValueError("JSON content identity must be text")
    artifacts = (
        (
            "comparisons.csv",
            "All quantity/component comparison states",
            export_comparisons_csv(evidence).encode("utf-8"),
        ),
        (
            "case_ledger.csv",
            "One row per adapter case",
            export_case_ledger_csv(evidence).encode("utf-8"),
        ),
    )
    rows: list[tuple[object, ...]] = [
        (name, purpose, len(content), hashlib.sha256(content).hexdigest())
        for name, purpose, content in artifacts
    ]
    rows.insert(
        0,
        (
            "validation_evidence.json",
            "Canonical structured evidence; volatile file hash is reported by the CLI",
            "varies with volatile block",
            f"{content_sha256} (canonical content)",
        ),
    )
    rows.append(
        (
            "validation_evidence.html",
            "This self-contained professor-facing report",
            "computed after write",
            "computed after write",
        )
    )
    return (
        _table(("Artifact", "Purpose", "Bytes", "SHA-256 / identity"), rows)
        + "<p>CSV text fields beginning with =, +, -, @, tab, or carriage return are prefixed with an apostrophe to prevent spreadsheet formula execution. Numeric cells are unchanged.</p>"
    )


_STYLE = """
:root{--ink:#17262d;--muted:#5d6b70;--paper:#f7f5ef;--panel:#fff;--line:#cfd9da;--accent:#087f8c;--warn:#a45220;--diagnostic:#4d326d}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Arial,sans-serif}header,main,footer{width:min(1180px,calc(100% - 32px));margin:auto}header{padding:54px 0 28px;border-bottom:2px solid var(--ink)}h1{font:700 clamp(2rem,5vw,4.4rem)/.98 Georgia,serif;letter-spacing:-.04em;max-width:900px;margin:0 0 18px}h2{font:700 clamp(1.45rem,3vw,2.15rem)/1.08 Georgia,serif;margin:0 0 18px}h3{margin:1.2rem 0 .5rem}p{max-width:92ch}main{padding:24px 0 72px}section{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:clamp(18px,4vw,36px);margin:18px 0}.lede{font-size:1.15rem}.role-line,.limitation{border-left:4px solid var(--accent);padding:12px 16px;background:#eef6f5}.warning{border-left:5px solid var(--warn);background:#fff6eb}.callout{padding:14px 18px;margin:18px 0}.diagnostics{border:3px solid var(--diagnostic);background:#faf7ff}.diagnostics h2{color:var(--diagnostic);text-transform:uppercase}.legacy{border:3px double var(--warn);background:#fffaf1}.dirty{background:#772a24;color:white;padding:14px 18px;font-weight:700;margin:18px 0}.table-wrap{overflow-x:auto;margin:16px 0;max-width:100%}table{border-collapse:collapse;width:100%;min-width:720px;font-size:.88rem}caption{text-align:left;font-weight:700;padding:0 0 8px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:9px 10px}th{background:#edf2f1;position:sticky;top:0}code,pre{font-family:Consolas,monospace;overflow-wrap:anywhere}pre{white-space:pre-wrap;max-height:420px;overflow:auto;background:#f0f2f2;padding:12px}details{border-top:1px solid var(--line);padding:9px 0}summary{cursor:pointer;font-weight:700}.figure-card{border-top:1px solid var(--line);padding:18px 0}.caption{color:var(--muted);font-size:.9rem}a{color:#046977;text-underline-offset:2px}footer{padding:24px 0 48px;color:var(--muted)}@media(max-width:520px){header,main,footer{width:min(100% - 18px,1180px)}header{padding-top:32px}section{padding:16px;margin:10px 0}.js-plotly-plot{min-width:0!important}.plot-container,.svg-container{width:100%!important}table{font-size:.82rem}}
"""


def render_html(evidence: ValidationEvidence) -> str:
    """Render one offline document with Plotly inlined exactly once."""

    dirty = ""
    if evidence.reproducibility.tree_state == "DIRTY":
        dirty = '<div class="dirty">Not reproducible from a commit alone.</div>'
    elif evidence.reproducibility.tree_state == "UNKNOWN":
        dirty = '<div class="dirty">Repository tree state is UNKNOWN; cleanliness is not established.</div>'
    volatile = (
        "<!-- VOLATILE START -->"
        f'<p class="caption">Run {_e(evidence.volatile.run_id)} · generated {_e(evidence.volatile.generated_at_utc.isoformat().replace("+00:00", "Z"))}</p>'
        "<!-- VOLATILE END -->"
    )
    sections = (
        _section("summary", "Scientific Summary", _summary(evidence))
        + _section("scope", "Validation Scope", _scope(evidence))
        + _section("dataset-role", "Dataset Role", _dataset_role(evidence))
        + _section("conditions", "Dataset Conditions", _conditions(evidence))
        + _section("solver-coverage", "Solver Coverage", _solver_coverage(evidence))
        + _section("failures", "Failures", _failures(evidence))
        + _section(
            "comparison-coverage", "Comparison Coverage", _comparison_coverage(evidence)
        )
        + _section("accuracy", "Accuracy", _accuracy(evidence))
        + _section("uncertainty", "Uncertainty", _uncertainty(evidence))
        + _section("figures", "Figures F1–F7", _figures(evidence))
        + _section("worst-cases", "Worst Cases", _worst_cases(evidence))
        + _section(
            "unavailable", "Unavailable / Not Assessable", _unavailable(evidence)
        )
        + _section("sensitivity", "Sensitivity", _sensitivity(evidence))
        + _section(
            "legacy", "Legacy Descriptive Statistics", _legacy(evidence), "legacy"
        )
        + _section(
            "diagnostics",
            "RETROSPECTIVE DIAGNOSTICS — NOT PRODUCTION PREDICTIONS",
            _diagnostics(evidence),
            "diagnostics",
        )
        + _section("limitations", "Limitations", _limitations())
        + _section(
            "model-configuration", "Model Configuration", _model_configuration(evidence)
        )
        + _section("provenance", "Provenance", _provenance(evidence))
        + _section(
            "software-verification",
            "Software Verification",
            _software_verification(evidence),
        )
        + _section("reproducibility", "Reproducibility", _reproducibility(evidence))
        + _section("inventory", "Artifact Inventory", _inventory(evidence))
    )
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>OpenPhase Module 17 Validation Evidence</title>"
        f"<style>{_STYLE}</style><script>{plotly_javascript()}</script></head><body>"
        "<header><p>OPENPHASE · VALIDATION EVIDENCE · V2-01-D</p>"
        "<h1>Module 17 experimental validation evidence</h1>"
        "<p>Peng–Robinson bubble- and dew-point comparisons for methane + ethane and methane + propane.</p>"
        f"{dirty}{volatile}</header><main>{sections}</main>"
        "<footer>OpenPhase validation evidence · descriptive scientific reporting, not an acceptance gate.</footer>"
        "</body></html>"
    )
    if re.search(
        r"<(?:link|img|iframe)\b|<script[^>]+src=", document, flags=re.IGNORECASE
    ):
        raise ValueError("self-contained report attempted an external resource load")
    return document
