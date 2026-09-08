"""Printable engineering reports over already-adapted calculation results.

The renderer accepts only the calculation-free dictionaries produced by the
existing export adapters.  It has no access to a scientific API and therefore
cannot start or repeat a calculation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html import escape
from importlib.metadata import PackageNotFoundError, version
from typing import Final

from pvt_phase_simulator.eos.phase_envelope import EnvelopeTerminationReason
from pvt_phase_simulator_ui.model_scope import ModelScope, RecordedSource

REPORT_FORMAT_VERSION: Final = "1.0.0"
_PACKAGE_NAME: Final = "pvt-phase-simulator"

#: A branch that stopped because the continuation itself broke down. Any points
#: already accepted stay valid, but the branch is not a completed traverse.
_TERMINATION_FAILED: Final = frozenset(
    {
        EnvelopeTerminationReason.CORRECTOR_FAILED.value,
        EnvelopeTerminationReason.BRANCH_LOST.value,
        EnvelopeTerminationReason.NUMERICAL_FAILURE.value,
    }
)

#: The continuation ran out of step before it could accept another point. The
#: engine's own message for it is "Minimum temperature step reached without an
#: acceptable correction", so this is a numerical limitation, not a normal end:
#: reporting it like a completed traverse would misrepresent the calculation.
_TERMINATION_INCOMPLETE: Final = frozenset(
    {EnvelopeTerminationReason.MINIMUM_STEP_REACHED.value}
)

#: Reasons a branch may stop having done what was asked of it.
_TERMINATION_NORMAL: Final = frozenset(
    {
        EnvelopeTerminationReason.TARGET_REACHED.value,
        EnvelopeTerminationReason.MAXIMUM_POINTS.value,
        EnvelopeTerminationReason.NEAR_CRITICAL.value,
        EnvelopeTerminationReason.PRESSURE_OUT_OF_BOUNDS.value,
    }
)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _enum_text(value: object) -> str:
    if value is None or str(value).strip() == "":
        return "Unavailable"
    return str(value).replace("_", " ").strip().capitalize()


def _number(value: object) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, int):
        return str(value)
    if value is None or str(value).strip() == "":
        return "Unavailable"
    return str(value)


def _status(label: str, detail: str, css_class: str) -> str:
    return (
        f'<span class="status {escape(css_class)}">{escape(label)}</span>'
        f" <span>{escape(detail)}</span>"
    )


def _unavailable(reason: str) -> str:
    return _status("UNAVAILABLE", reason, "unavailable")


def _failed(reason: str) -> str:
    return _status("FAILED", reason, "failed")


def _not_applicable(reason: str) -> str:
    return _status("NOT APPLICABLE", reason, "not-applicable")


def _incomplete(reason: str) -> str:
    return _status("INCOMPLETE", reason, "incomplete")


def _available(value: object, unit: str | None = None) -> str:
    rendered = escape(_number(value))
    if unit:
        rendered = f"{rendered} {escape(unit)}"
    return rendered


def _optional_record(
    value: object,
    *,
    unit: str | None = None,
    failed_reason: str | None = None,
) -> str:
    if failed_reason is not None:
        return _failed(failed_reason)
    record = _mapping(value)
    status = str(record.get("status", "unavailable"))
    item = record.get("value")
    reason = str(record.get("reason") or "The result did not supply this field.")
    if status == "available" and item is not None:
        return _available(item, unit)
    if status == "not_applicable":
        return _not_applicable(reason)
    return _unavailable(reason)


def _row(label: str, value: str) -> str:
    return f'<tr><th scope="row">{escape(label)}</th><td>{value}</td></tr>'


def _table(rows: Sequence[tuple[str, str]]) -> str:
    return (
        '<table class="key-values"><tbody>'
        + "".join(_row(label, value) for label, value in rows)
        + "</tbody></table>"
    )


def _section(title: str, body: str, *, section_id: str) -> str:
    return (
        f'<section id="{escape(section_id)}"><h2>{escape(title)}</h2>{body}</section>'
    )


def _result_unavailable_rows(
    fields: Sequence[str], reason: str = "This calculation has not been run."
) -> str:
    return _table([(field, _unavailable(reason)) for field in fields])


def _package_version() -> str | None:
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return None


def _component_names(document: Mapping[str, object]) -> tuple[str, ...]:
    case = _mapping(document.get("case"))
    names = tuple(
        str(_mapping(component).get("name") or f"Component {index}")
        for index, component in enumerate(_sequence(case.get("components")), start=1)
    )
    return names or ("Component unavailable",)


def _case_section(document: Mapping[str, object]) -> str:
    case = _mapping(document.get("case"))
    components = _sequence(case.get("components"))
    component_rows = []
    for component in components:
        item = _mapping(component)
        component_rows.append(
            "<tr>"
            f'<th scope="row">{escape(str(item.get("name") or "Unavailable"))}</th>'
            f"<td>{_available(item.get('composition_mol_percent'), 'mol %')}</td>"
            f"<td>{_available(item.get('overall_mole_fraction'), 'mol/mol')}</td>"
            "</tr>"
        )
    if not component_rows:
        component_table = _unavailable("No fluid composition was supplied.")
    else:
        component_table = (
            "<table><thead><tr><th>Component</th><th>Composition</th>"
            "<th>Overall mole fraction</th></tr></thead><tbody>"
            + "".join(component_rows)
            + "</tbody></table>"
        )
    temperature_unit = str(case.get("temperature_unit") or "unit unavailable")
    pressure_unit = str(case.get("pressure_unit") or "unit unavailable")
    body = _table(
        [
            ("Model", _available(case.get("model"))),
            (
                "Binary interactions",
                _available(case.get("binary_interaction_assumption")),
            ),
            (
                "Temperature (presentation)",
                _available(case.get("temperature"), temperature_unit),
            ),
            (
                "Pressure (presentation)",
                _available(case.get("pressure"), pressure_unit),
            ),
            ("Temperature (engine)", _available(case.get("temperature_k"), "K")),
            ("Pressure (engine)", _available(case.get("pressure_pa"), "Pa")),
        ]
    )
    body += "<h3>Fluid composition</h3>" + component_table
    return _section("Calculation inputs", body, section_id="inputs")


def _flash_is_usable(flash: Mapping[str, object]) -> bool:
    solver = str(flash.get("solver_status"))
    phase = str(flash.get("phase_classification"))
    stability = str(flash.get("phase_stability_status"))
    if solver == "converged":
        return True
    single_z = _mapping(flash.get("selected_single_phase_z"))
    return (
        solver == "not_attempted"
        and phase == "single_phase"
        and stability == "stable"
        and single_z.get("status") == "available"
        and single_z.get("value") is not None
    )


def _composition_cell(record: object, index: int, failed_reason: str | None) -> str:
    if failed_reason is not None:
        return _failed(failed_reason)
    value_record = _mapping(record)
    status = str(value_record.get("status", "unavailable"))
    reason = str(
        value_record.get("reason") or "The result did not supply this composition."
    )
    if status == "not_applicable":
        return _not_applicable(reason)
    values = _sequence(value_record.get("value"))
    if status != "available" or index >= len(values):
        return _unavailable(reason)
    return _available(values[index], "mol/mol")


def _flash_section(document: Mapping[str, object]) -> str:
    results = _mapping(document.get("results"))
    flash = _mapping(results.get("flash"))
    if flash.get("calculation_status") != "calculated":
        body = _status(
            "UNAVAILABLE", "The flash calculation has not been run.", "unavailable"
        )
        body += _result_unavailable_rows(
            (
                "Phase classification",
                "Phase-stability status",
                "Flash solver status",
                "Two-phase split required",
                "Liquid fraction",
                "Vapor fraction",
                "Liquid Z",
                "Vapor Z",
                "Single-phase Z",
                "Phase compositions",
            )
        )
        return _section("Phase stability and flash", body, section_id="flash")

    usable = _flash_is_usable(flash)
    failure_reason = str(
        flash.get("termination_or_failure_reason")
        or "The calculation did not produce a usable converged result."
    )
    failed_reason = None if usable else failure_reason
    phase = str(flash.get("phase_classification") or "unavailable")
    solver = str(flash.get("solver_status") or "unavailable")
    stability = str(flash.get("phase_stability_status") or "unavailable")
    if usable and phase == "single_phase":
        disposition = _status(
            "AVAILABLE",
            "Stable single-phase result; a two-phase flash iteration was not "
            "applicable.",
            "available",
        )
    elif usable:
        disposition = _status(
            "CONVERGED", "Usable two-phase flash result.", "available"
        )
    else:
        disposition = _failed(failure_reason)

    termination = flash.get("termination_or_failure_reason")
    if termination:
        termination_text = _available(termination)
    elif usable:
        termination_text = _not_applicable(
            "No termination or failure reason was reported for this usable result."
        )
    else:
        termination_text = _failed(
            "No termination or failure reason was supplied by the failed result."
        )

    phase_text = (
        _available(_enum_text(phase))
        if usable
        else _failed("Phase classification is not reported as a usable result.")
    )
    split_required = flash.get("two_phase_split_required")
    if not usable:
        split_text = _failed("A usable phase split was not produced.")
    elif isinstance(split_required, bool):
        split_text = _available(split_required)
    else:
        split_text = _optional_record(split_required)
    rows = [
        ("Result disposition", disposition),
        ("Phase classification", phase_text),
        ("Phase-stability status", _available(_enum_text(stability))),
        ("Flash solver status", _available(_enum_text(solver))),
        ("Two-phase split required", split_text),
        ("Termination / failure reason", termination_text),
        ("Iteration count", _available(flash.get("iteration_count"), "iterations")),
        (
            "Liquid fraction",
            _optional_record(
                flash.get("liquid_fraction"),
                unit="mol/mol",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Vapor fraction",
            _optional_record(
                flash.get("vapor_fraction"),
                unit="mol/mol",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Liquid Z",
            _optional_record(
                flash.get("liquid_z"),
                unit="dimensionless",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Vapor Z",
            _optional_record(
                flash.get("vapor_z"),
                unit="dimensionless",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Selected single-phase Z",
            _optional_record(
                flash.get("selected_single_phase_z"),
                unit="dimensionless",
                failed_reason=failed_reason,
            ),
        ),
    ]
    body = _table(rows)
    body += "<h3>Source-provided phase compositions</h3>"
    composition_rows = []
    for index, name in enumerate(_component_names(document)):
        liquid = _composition_cell(
            flash.get("liquid_composition"), index, failed_reason
        )
        vapor = _composition_cell(flash.get("vapor_composition"), index, failed_reason)
        composition_rows.append(
            "<tr>"
            f'<th scope="row">{escape(name)}</th>'
            f"<td>{liquid}</td>"
            f"<td>{vapor}</td>"
            "</tr>"
        )
    body += (
        "<table><thead><tr><th>Component</th><th>Liquid composition</th>"
        "<th>Vapor composition</th></tr></thead><tbody>"
        + "".join(composition_rows)
        + "</tbody></table>"
    )
    return _section("Phase stability and flash", body, section_id="flash")


def _composition_summary(value: object, component_names: Sequence[str]) -> str:
    values = _sequence(value)
    if not values:
        return "Unavailable"
    pairs = [
        f"{name}={_number(item)}"
        for name, item in zip(component_names, values, strict=False)
    ]
    return "; ".join(pairs) + " mol/mol"


def _termination_failed(status: str) -> bool:
    """Whether the branch ended in a structured failure.

    Matched against the engine's actual termination values rather than by
    searching the text for "failed". Substring matching silently passed
    ``minimum_step_reached`` off as a normal ending even though the engine
    produces it only when a retry loop accepted no point at all.
    """

    return status in _TERMINATION_FAILED


def _termination_incomplete(status: str) -> bool:
    """Whether the branch stopped short of completing, without failing outright."""

    return status in _TERMINATION_INCOMPLETE


def _envelope_branch(
    branch: Mapping[str, object], label: str, component_names: Sequence[str]
) -> str:
    termination = str(branch.get("termination_status") or "unavailable")
    message = str(
        branch.get("termination_message") or "No termination message was supplied."
    )
    accepted = branch.get("accepted_point_count")
    rejected = branch.get("rejected_attempt_count")
    rows = [
        ("Termination status", _available(_enum_text(termination))),
        ("Termination message", _available(message)),
        ("Accepted points", _available(accepted, "points")),
        ("Rejected attempts", _available(rejected, "attempts")),
    ]
    body = f"<h3>{escape(label)} branch</h3>" + _table(rows)
    if _termination_failed(termination):
        body += _failed(
            "The branch ended with a structured failure; any preceding converged "
            "points remain listed individually."
        )
    elif _termination_incomplete(termination):
        body += _incomplete(
            "The branch stopped before completing its traverse: the continuation "
            "could not accept a further point at the minimum step. Any points "
            "listed below are converged, but this branch is not a complete "
            "envelope traverse and must not be read as one."
        )

    points = _sequence(branch.get("points"))
    if not points:
        if _termination_failed(termination):
            marker = _failed(message)
        elif _termination_incomplete(termination):
            marker = _incomplete(message)
        else:
            marker = _unavailable(
                "No converged output points were supplied for this branch."
            )
        return body + f'<p class="notice">{marker}</p>'

    point_rows = []
    for index, raw_point in enumerate(points, start=1):
        point = _mapping(raw_point)
        status = str(point.get("status") or "unavailable")
        converged = status == "converged"
        if converged:
            temperature = _available(
                point.get("temperature"), str(point.get("temperature_unit") or "")
            )
            pressure = _available(
                point.get("pressure"), str(point.get("pressure_unit") or "")
            )
            parent = escape(
                _composition_summary(point.get("parent_composition"), component_names)
            )
            incipient = escape(
                _composition_summary(
                    point.get("incipient_composition"), component_names
                )
            )
        else:
            reason = f"Envelope point status was {_enum_text(status)}."
            temperature = pressure = parent = incipient = _failed(reason)
        point_rows.append(
            "<tr>"
            f"<td>{index}</td><td>{escape(_enum_text(status))}</td>"
            f"<td>{temperature}</td><td>{pressure}</td>"
            f"<td>{parent}</td><td>{incipient}</td>"
            "</tr>"
        )
    body += (
        '<div class="table-scroll"><table><thead><tr><th>Point</th><th>Status</th>'
        "<th>Temperature</th><th>Pressure</th><th>Parent composition</th>"
        "<th>Incipient composition</th></tr></thead><tbody>"
        + "".join(point_rows)
        + "</tbody></table></div>"
    )
    return body


def _envelope_section(document: Mapping[str, object]) -> str:
    results = _mapping(document.get("results"))
    envelope = _mapping(results.get("phase_envelope"))
    if envelope.get("calculation_status") != "calculated":
        reason = "The phase-envelope calculation has not been run."
        body = _status("UNAVAILABLE", reason, "unavailable")
        body += _result_unavailable_rows(("Bubble outputs", "Dew outputs"), reason)
        return _section("Bubble and dew outputs", body, section_id="envelope")
    component_names = _component_names(document)
    body = _envelope_branch(
        _mapping(envelope.get("bubble_branch")), "Bubble", component_names
    )
    body += _envelope_branch(
        _mapping(envelope.get("dew_branch")), "Dew", component_names
    )
    return _section("Bubble and dew outputs", body, section_id="envelope")


def _critical_section(document: Mapping[str, object]) -> str:
    results = _mapping(document.get("results"))
    critical = _mapping(results.get("critical_point"))
    fields = (
        "Solver status",
        "Certification",
        "Termination reason",
        "Critical temperature",
        "Critical pressure",
        "lambda_min",
        "Cubic coefficient",
        "Scaled residual norm",
        "Critical direction",
    )
    if critical.get("calculation_status") != "calculated":
        reason = "The production critical-point solve has not been run."
        body = _status("UNAVAILABLE", reason, "unavailable")
        body += _result_unavailable_rows(fields, reason)
        return _section("Critical point", body, section_id="critical")

    certified = critical.get("certified") is True
    solver_status = str(critical.get("solver_status") or "unavailable")
    valid = certified and solver_status == "converged"
    failure_reason = str(
        critical.get("termination_reason")
        or "The solve did not return a certified critical point."
    )
    failed_reason = (
        None
        if valid
        else ("No certified critical value is available: " + failure_reason)
    )
    certification = (
        _status(
            "CERTIFIED",
            "CriticalPointStatus.CONVERGED is present.",
            "available",
        )
        if valid
        else _failed(
            "CriticalPointStatus.CONVERGED is absent; this is not a certified "
            "critical point."
        )
    )
    temperature_unit = str(critical.get("temperature_unit") or "unit unavailable")
    pressure_unit = str(critical.get("pressure_unit") or "unit unavailable")
    rows = [
        ("Solver status", _available(_enum_text(solver_status))),
        ("Certification", certification),
        ("Termination reason", _available(failure_reason)),
        (
            "Iteration count",
            _available(critical.get("iteration_count"), "iterations"),
        ),
        (
            "Critical temperature",
            _optional_record(
                critical.get("temperature"),
                unit=temperature_unit,
                failed_reason=failed_reason,
            ),
        ),
        (
            "Critical pressure",
            _optional_record(
                critical.get("pressure"),
                unit=pressure_unit,
                failed_reason=failed_reason,
            ),
        ),
        (
            "Critical temperature (engine)",
            _optional_record(
                critical.get("temperature_k"),
                unit="K",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Critical pressure (engine)",
            _optional_record(
                critical.get("pressure_pa"),
                unit="Pa",
                failed_reason=failed_reason,
            ),
        ),
        (
            "lambda_min",
            _optional_record(
                critical.get("lambda_min"),
                unit="dimensionless",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Cubic coefficient",
            _optional_record(
                critical.get("cubic_coefficient"),
                unit="dimensionless",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Scaled residual norm",
            _optional_record(
                critical.get("scaled_residual_norm"),
                unit="dimensionless",
                failed_reason=failed_reason,
            ),
        ),
        (
            "Critical direction",
            _optional_record(
                critical.get("critical_direction"),
                unit="dimensionless",
                failed_reason=failed_reason,
            ),
        ),
    ]
    return _section("Critical point", _table(rows), section_id="critical")


def _sweep_section(sweep_document: Mapping[str, object] | None) -> str:
    fields = (
        "Sweep kind",
        "Fixed condition",
        "Requested range",
        "Requested points",
        "Calculated points",
        "Failed points",
    )
    if sweep_document is None:
        reason = "No engineering sweep has been calculated for this case."
        body = _status("UNAVAILABLE", reason, "unavailable")
        body += _result_unavailable_rows(fields, reason)
        return _section("Engineering sweep summary", body, section_id="sweep")

    request = _mapping(sweep_document.get("request"))
    summary = _mapping(sweep_document.get("summary"))
    kind = str(request.get("kind") or "unavailable")
    requested = summary.get("requested_points")
    calculated = summary.get("calculated_points")
    failed = summary.get("failed_points")
    if isinstance(failed, int) and isinstance(requested, int) and failed == requested:
        disposition = _failed("Every requested sweep point failed.")
    elif isinstance(failed, int) and failed > 0:
        disposition = _status(
            "PARTIAL",
            f"{failed} requested point(s) failed and remain failed.",
            "unavailable",
        )
    else:
        disposition = _status(
            "AVAILABLE", "All requested sweep points were calculated.", "available"
        )

    if kind == "pressure":
        sweep_unit = str(request.get("sweep_unit") or "unit unavailable")
        fixed = _available(
            request.get("fixed_temperature"),
            str(request.get("fixed_temperature_unit") or "unit unavailable"),
        )
    elif kind == "temperature":
        sweep_unit = str(request.get("sweep_unit") or "unit unavailable")
        fixed = _available(
            request.get("fixed_pressure"),
            str(request.get("fixed_pressure_unit") or "unit unavailable"),
        )
    else:
        sweep_unit = "unit unavailable"
        fixed = _unavailable("The sweep kind was not supplied.")
    requested_range = (
        f"{_available(request.get('start'))} to {_available(request.get('end'))} "
        f"{escape(sweep_unit)}"
    )
    body = _table(
        [
            ("Result disposition", disposition),
            ("Sweep kind", _available(_enum_text(kind))),
            ("Fixed condition", fixed),
            ("Requested range", requested_range),
            ("Requested points", _available(requested, "points")),
            ("Calculated points", _available(calculated, "points")),
            ("Failed points", _available(failed, "points")),
        ]
    )
    body += (
        '<p class="notice">Failed and unavailable sweep values are not interpolated, '
        "replaced, or presented as calculated results.</p>"
    )
    return _section("Engineering sweep summary", body, section_id="sweep")


def _doi(source: RecordedSource) -> str:
    if source.doi is None:
        return _unavailable("DOI was not supplied by the repository record.")
    doi = escape(source.doi)
    return f'<a href="https://doi.org/{doi}">DOI {doi}</a>'


def _scope_section(scope: ModelScope) -> str:
    property_sources = "".join(
        "<li>"
        f"<strong>{escape(source.name)}</strong>: {escape(source.citation)} "
        f"({_doi(source)})"
        "</li>"
        for source in scope.property_sources
    )
    if not property_sources:
        property_sources = (
            f"<li>{_unavailable('No property sources were recorded.')}</li>"
        )
    systems = ", ".join(scope.validation_system_names) or "Unavailable"
    components = ", ".join(scope.verified_component_names) or "Unavailable"
    temperature_range = (
        f"{_number(scope.validation_temperature_range_k[0])} to "
        f"{_number(scope.validation_temperature_range_k[1])} K"
    )
    pressure_range = (
        f"{_number(scope.validation_pressure_range_pa[0])} to "
        f"{_number(scope.validation_pressure_range_pa[1])} Pa"
    )
    body = _table(
        [
            ("EOS", _available(scope.eos_name)),
            ("Verified component scope", _available(components)),
            ("Binary-interaction policy", _available(scope.interaction_policy.value)),
            (
                "Validation states",
                _available(scope.validation_state_count, "experimental VLE states"),
            ),
            ("Validation systems", _available(systems)),
            ("Recorded temperature range", escape(temperature_range)),
            ("Recorded pressure range", escape(pressure_range)),
            ("Validation artifact", _available(scope.validation_artifact.as_posix())),
        ]
    )
    body += "<h3>Model assumptions</h3>"
    body += (
        "<ul>"
        "<li>All omitted off-diagonal binary interactions use kij = 0; no fitted "
        "interaction parameters are used.</li>"
        "<li>Engine result units are kelvin (K) and pascal (Pa). Presentation "
        "conversions do not alter the stored scientific result.</li>"
        "<li>Only source-provided public result fields are rendered. Missing values "
        "remain unavailable.</li>"
        "</ul>"
    )
    body += "<h3>Known limitations</h3>"
    body += (
        "<ul>"
        "<li>Validation evidence covers only the recorded systems and state range; "
        "it does not establish accuracy for other mixtures or conditions.</li>"
        "<li>Envelope continuation is bounded and may return unavailable branches "
        "or structured terminations.</li>"
        "<li>Only CriticalPointStatus.CONVERGED is a certified critical point. "
        "Turning points and a zero lambda_min alone are not labelled critical "
        "points.</li>"
        "<li>No reservoir depletion, CCE/CVD, separator trains, pseudocomponents or "
        "C7+, EOS tuning, kij fitting, new-component support, or arbitrary "
        "reservoir-fluid validation is provided.</li>"
        "<li>This report is not a substitute for engineering review.</li>"
        "</ul>"
    )
    body += "<h3>Recorded provenance</h3><ul>" + property_sources
    body += (
        "<li><strong>Experimental validation — "
        f"{escape(scope.validation_source.name)}</strong>: "
        f"{escape(scope.validation_source.citation)} "
        f"({_doi(scope.validation_source)})</li></ul>"
    )
    return _section("Model, limitations, and provenance", body, section_id="scope")


def export_engineering_report_html(
    document: Mapping[str, object],
    *,
    scope: ModelScope,
    sweep_document: Mapping[str, object] | None = None,
    generated_at: datetime | None = None,
    application_version: str | None = None,
    case_identifier: str = "Current submitted case",
) -> bytes:
    """Render adapted, already-computed results as a printable HTML report."""

    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    timestamp_text = (
        timestamp.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    metadata = _mapping(document.get("metadata"))
    schema = _mapping(document.get("schema"))
    app_version = (
        application_version if application_version is not None else (_package_version())
    )
    version_text = (
        _available(app_version)
        if app_version
        else _unavailable("Installed package version metadata was not found.")
    )
    identity = _table(
        [
            ("Case identification", _available(case_identifier)),
            ("Report generated", _available(timestamp_text, "UTC")),
            ("Application version", version_text),
            ("Report format version", _available(REPORT_FORMAT_VERSION)),
            (
                "Source export schema",
                _available(
                    f"{schema.get('name', 'Unavailable')} "
                    f"v{schema.get('version', 'Unavailable')}"
                ),
            ),
            (
                "Engine units",
                _available(
                    ", ".join(
                        f"{key}: {value}"
                        for key, value in _mapping(metadata.get("engine_units")).items()
                    )
                    or "Unavailable"
                ),
            ),
        ]
    )
    source_notice = (
        '<p class="source-note"><strong>Result source.</strong> This report renders '
        "the current case's already-computed, non-stale session results. Report "
        "generation does not start or repeat a scientific calculation.</p>"
    )
    sections = "".join(
        (
            _section(
                "Case identification", identity + source_notice, section_id="case"
            ),
            _case_section(document),
            _flash_section(document),
            _envelope_section(document),
            _critical_section(document),
            _sweep_section(sweep_document),
            _scope_section(scope),
        )
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenPhase engineering case report</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#5e6878;
      --line:#d7dde6; --paper:#ffffff; --panel:#f5f7fa; --accent:#0b5cab;
      --ok:#176b3a; --warn:#8a5a00; --bad:#a12622; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:#eef1f5; color:var(--ink);
      font:14px/1.5 "Segoe UI", Arial, sans-serif; }}
    main {{ width:min(1120px, calc(100% - 32px)); margin:32px auto;
      padding:44px; background:var(--paper); box-shadow:0 8px 30px #17203318; }}
    header {{ padding-bottom:22px; border-bottom:3px solid var(--accent); }}
    .eyebrow {{ margin:0 0 5px; color:var(--accent); font-size:12px;
      font-weight:700; letter-spacing:.12em; text-transform:uppercase; }}
    h1 {{ margin:0; font-size:32px; line-height:1.15; }}
    h2 {{ margin:0 0 14px; font-size:21px; }}
    h3 {{ margin:22px 0 9px; font-size:15px; }}
    section {{ padding:24px 0; border-bottom:1px solid var(--line);
      break-inside:auto; }}
    table {{ width:100%; border-collapse:collapse; margin:10px 0; }}
    th, td {{ padding:9px 10px; border:1px solid var(--line);
      vertical-align:top; text-align:left; }}
    thead th {{ background:var(--panel); font-size:12px; letter-spacing:.03em; }}
    .key-values th {{ width:34%; background:var(--panel); }}
    .status {{ display:inline-block; padding:1px 7px; border-radius:999px;
      font-size:11px; font-weight:750; letter-spacing:.04em; }}
    .available {{ color:var(--ok); background:#e9f6ee; }}
    .unavailable, .not-applicable, .incomplete {{ color:var(--warn);
      background:#fff3d6; }}
    .failed {{ color:var(--bad); background:#fdebea; }}
    .source-note, .notice {{ padding:12px 14px; background:var(--panel);
      border-left:4px solid var(--accent); }}
    .table-scroll {{ overflow-x:auto; }}
    a {{ color:var(--accent); }}
    footer {{ padding-top:22px; color:var(--muted); font-size:12px; }}
    @page {{ size:A4 landscape; margin:12mm; }}
    @media print {{
      body {{ background:#fff; font-size:10pt; }}
      main {{ width:auto; margin:0; padding:0; box-shadow:none; }}
      section, table, tr {{ break-inside:avoid; }}
      a {{ color:inherit; text-decoration:none; }}
    }}
  </style>
</head>
<body>
<main>
  <header><p class="eyebrow">OpenPhase · Engineering record</p>
    <h1>Engineering case report</h1></header>
  {sections}
  <footer>Generated from existing OpenPhase result adapters. No values are
  interpolated or recomputed by this report.</footer>
</main>
</body>
</html>
"""
    return html.encode("utf-8")
