"""Focused tests for the strict provenanced component-property database."""

from __future__ import annotations

import csv
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pvt_phase_simulator.component_database import (
    DATABASE_HEADER,
    DEFAULT_COMPONENT_DATABASE_PATH,
    ComponentDatabaseError,
    UnsupportedComponentError,
    get_component,
    list_components,
    load_component_database,
    resolve_component,
)
from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.mixing_rules import (
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import calculate_compressibility_roots
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeBranchKind,
    EnvelopeContinuationSettings,
    trace_phase_envelope_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    ComponentPropertyName,
    FluidMixture,
    MixtureComponent,
    PropertySourceStatus,
)

PRE_MODULE_16_1_PROVISIONAL_VALUES = {
    "methane": ("Methane", 190.56, 4_599_200.0, 0.011),
    "ethane": ("Ethane", 305.32, 4_872_000.0, 0.099),
    "propane": ("Propane", 369.83, 4_248_000.0, 0.152),
}
SOURCED_VALUES = {
    "methane": ("Methane", 190.564, 4_599_200.0, 0.011420),
    "ethane": ("Ethane", 305.322, 4_872_200.0, 0.099500),
    "propane": ("Propane", 369.890, 4_251_200.0, 0.152100),
}
SOURCE_REFERENCE_NAME = "Yang & Richter (2025), Journal of Chemical & Engineering Data"
SOURCE_DOI = "10.1021/acs.jced.5c00110"
SOURCE_RECORDS = {
    "methane": "74-82-8",
    "ethane": "74-84-0",
    "propane": "74-98-6",
}
PROJECT_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "component_properties.csv"
)
PROVENANCE_PLACEHOLDER_INPUTS = (
    "N/A",
    "n/a",
    "NA",
    "None",
    "null",
    "unknown",
    "UNSPECIFIED",
    "not available",
    "not applicable",
    "missing",
    "TBD",
    "to be determined",
    "   ",
)


def _rows() -> list[dict[str, str]]:
    with DEFAULT_COMPONENT_DATABASE_PATH.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _write_database(
    path: Path,
    rows: list[dict[str, str]],
    header: tuple[str, ...] = DATABASE_HEADER,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _clear_traceability_evidence(row: dict[str, str]) -> None:
    for field in ("property_source_identity", "citation_text", "url", "doi"):
        row[field] = ""


def test_default_database_loads_all_components_in_stable_order() -> None:
    database = load_component_database()
    assert tuple(record.component_id for record in database.records) == (
        "methane",
        "ethane",
        "propane",
    )
    assert database.records == load_component_database().records


def test_project_database_and_packaged_runtime_copy_are_byte_identical() -> None:
    assert (
        PROJECT_DATABASE_PATH.read_bytes()
        == DEFAULT_COMPONENT_DATABASE_PATH.read_bytes()
    )


@pytest.mark.parametrize(
    ("identifier", "expected_id"),
    [
        ("methane", "methane"),
        ("Methane", "methane"),
        (" CH4 ", "methane"),
        ("c1", "methane"),
        ("C2H6", "ethane"),
        ("c2", "ethane"),
        ("C3H8", "propane"),
        ("c3", "propane"),
    ],
)
def test_deliberate_aliases_resolve_deterministically(
    identifier: str, expected_id: str
) -> None:
    assert resolve_component(identifier).component_id == expected_id


def test_default_api_returns_immutable_ordered_records() -> None:
    records = list_components()
    assert isinstance(records, tuple)
    assert get_component("methane") is METHANE
    with pytest.raises(FrozenInstanceError):
        records[0].component_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        records[0].component.critical_temperature_k = 1.0


@pytest.mark.parametrize(
    ("component_id", "constant"),
    [("methane", METHANE), ("ethane", ETHANE), ("propane", PROPANE)],
)
def test_loaded_values_exactly_equal_verified_source_values(
    component_id: str, constant: object
) -> None:
    component = get_component(component_id)
    name, temperature, pressure, acentric = SOURCED_VALUES[component_id]
    assert component.name == name
    assert component.critical_temperature_k == temperature
    assert component.critical_pressure_pa == pressure
    assert component.acentric_factor == acentric
    assert repr(component.critical_temperature_k) == repr(temperature)
    assert repr(component.critical_pressure_pa) == repr(pressure)
    assert repr(component.acentric_factor) == repr(acentric)
    assert component is constant


def test_pre_module_16_1_provisional_values_remain_auditable() -> None:
    assert PRE_MODULE_16_1_PROVISIONAL_VALUES == {
        "methane": ("Methane", 190.56, 4_599_200.0, 0.011),
        "ethane": ("Ethane", 305.32, 4_872_000.0, 0.099),
        "propane": ("Propane", 369.83, 4_248_000.0, 0.152),
    }
    assert PRE_MODULE_16_1_PROVISIONAL_VALUES != SOURCED_VALUES


def test_every_property_exposes_exact_verified_source_provenance() -> None:
    expected = (
        (ComponentPropertyName.CRITICAL_TEMPERATURE, "K", "critical temperature"),
        (ComponentPropertyName.CRITICAL_PRESSURE, "Pa", "critical pressure"),
        (ComponentPropertyName.ACENTRIC_FACTOR, "1", "acentric factor"),
    )
    for record in list_components():
        assert record.component.provenance is not None
        provenance = record.component.provenance
        actual = (
            provenance.critical_temperature,
            provenance.critical_pressure,
            provenance.acentric_factor,
        )
        cas_number = SOURCE_RECORDS[record.component_id]
        for source, (property_name, unit, source_description) in zip(
            actual, expected, strict=True
        ):
            assert source.property_name is property_name
            assert source.canonical_unit == unit
            assert source.status is PropertySourceStatus.VERIFIED
            assert source.source_reference_name == SOURCE_REFERENCE_NAME
            assert source.doi == SOURCE_DOI
            assert source.citation_text is not None
            assert "Effective Thermophysical Constants" in source.citation_text
            assert source.property_source_identity is not None
            assert "Yang & Richter (2025) Table 5" in source.property_source_identity
            assert record.component.name in source.property_source_identity
            assert "Table S3 row" not in source.property_source_identity
            assert cas_number in source.property_source_identity
            assert source_description in source.property_source_identity
            assert "originally taken from REFPROP" in source.property_source_identity
            assert "no direct REFPROP query was made" in (source.notes or "")
            if property_name is ComponentPropertyName.CRITICAL_PRESSURE:
                assert source.original_unit == "kPa"
                assert source.conversion == "1 kPa = 1000 Pa"
            else:
                assert source.original_unit is None
                assert source.conversion is None


def test_table_5_pressure_values_convert_exactly_from_kpa_to_canonical_pa() -> None:
    source_pressures_kpa = {
        "methane": Decimal("4599.20"),
        "ethane": Decimal("4872.20"),
        "propane": Decimal("4251.20"),
    }
    for component_id, source_pressure_kpa in source_pressures_kpa.items():
        component = get_component(component_id)
        canonical_pressure_pa = source_pressure_kpa * Decimal(1000)
        assert canonical_pressure_pa == Decimal(str(component.critical_pressure_pa))


def test_default_path_does_not_depend_on_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_component_database().get_component("C1") == METHANE


def test_alternate_path_and_blank_lines_load(tmp_path: Path) -> None:
    path = tmp_path / "components.csv"
    _write_database(path, _rows())
    path.write_text("\n" + path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert load_component_database(path).records == load_component_database().records


def test_unsupported_component_and_blank_lookup_are_explicit() -> None:
    with pytest.raises(UnsupportedComponentError, match="Unsupported component"):
        get_component("methan")
    with pytest.raises(UnsupportedComponentError, match="blank"):
        get_component("  ")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("value", "", "missing required value"),
        ("value", "not-a-number", "invalid numeric value"),
        ("value", "NaN", "finite"),
        ("value", "inf", "finite"),
        ("source_status", "authoritative", "invalid source status"),
        ("unit", "bar", "requires unit"),
    ],
)
def test_malformed_field_is_rejected(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    rows = _rows()
    rows[0][field] = value
    path = tmp_path / "invalid.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match=message):
        load_component_database(path)


@pytest.mark.parametrize(
    ("property_name", "value", "message"),
    [
        ("critical_temperature", "0", "greater than zero"),
        ("critical_pressure", "-1", "greater than zero"),
        ("acentric_factor", "not-a-number", "invalid numeric value"),
    ],
)
def test_invalid_physical_value_is_rejected(
    tmp_path: Path, property_name: str, value: str, message: str
) -> None:
    rows = _rows()
    row = next(item for item in rows if item["property"] == property_name)
    row["value"] = value
    path = tmp_path / "invalid.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match=message):
        load_component_database(path)


def test_exact_header_rejects_missing_and_extra_columns(tmp_path: Path) -> None:
    rows = _rows()
    for header in (DATABASE_HEADER[:-1], (*DATABASE_HEADER, "unexpected")):
        path = tmp_path / f"header-{len(header)}.csv"
        _write_database(path, rows, header)
        with pytest.raises(ComponentDatabaseError, match="header must exactly match"):
            load_component_database(path)


def test_duplicate_property_row_is_rejected(tmp_path: Path) -> None:
    rows = _rows()
    rows.insert(1, rows[0].copy())
    path = tmp_path / "duplicate.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="duplicate critical_temperature"):
        load_component_database(path)


def test_duplicate_noncontiguous_component_id_is_rejected(tmp_path: Path) -> None:
    rows = _rows()
    rows.append(rows[0].copy())
    path = tmp_path / "duplicate-id.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="duplicate non-contiguous"):
        load_component_database(path)


def test_conflicting_alias_is_rejected(tmp_path: Path) -> None:
    rows = _rows()
    for row in rows[3:6]:
        row["aliases"] = "C1|C2"
    path = tmp_path / "alias.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="Ambiguous identifier or alias"):
        load_component_database(path)


def test_inconsistent_component_metadata_is_rejected(tmp_path: Path) -> None:
    rows = _rows()
    rows[1]["canonical_name"] = "Different"
    path = tmp_path / "metadata.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="inconsistent metadata"):
        load_component_database(path)


def test_missing_property_is_rejected(tmp_path: Path) -> None:
    rows = _rows()[1:]
    path = tmp_path / "missing.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="missing properties"):
        load_component_database(path)


@pytest.mark.parametrize("missing_field", ["original_unit", "conversion"])
def test_conversion_metadata_requires_complete_pair(
    tmp_path: Path, missing_field: str
) -> None:
    rows = _rows()
    rows[1][missing_field] = ""
    path = tmp_path / "conversion.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="must be supplied together"):
        load_component_database(path)


@pytest.mark.parametrize(
    ("row_index", "original_unit", "conversion"),
    [
        (0, "K", "identity"),
        (1, "MPa", "1 kPa = 1000 Pa"),
        (1, "kPa", "1 MPa = 1000000 Pa"),
        (1, "kPa", "multiply by 1000"),
    ],
)
def test_unsupported_conversion_metadata_is_rejected(
    tmp_path: Path,
    row_index: int,
    original_unit: str,
    conversion: str,
) -> None:
    rows = _rows()
    rows[row_index]["original_unit"] = original_unit
    rows[row_index]["conversion"] = conversion
    path = tmp_path / "conversion.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="unsupported source-unit"):
        load_component_database(path)


def test_supported_pressure_conversion_metadata_is_accepted() -> None:
    source = (
        load_component_database().get_component("methane").provenance.critical_pressure  # type: ignore[union-attr]
    )
    assert source.original_unit == "kPa"
    assert source.conversion == "1 kPa = 1000 Pa"


@pytest.mark.parametrize("source_name", PROVENANCE_PLACEHOLDER_INPUTS)
def test_verified_status_rejects_placeholder_source_names(
    tmp_path: Path, source_name: str
) -> None:
    rows = _rows()
    rows[0]["source_status"] = "verified"
    rows[0]["source_reference_name"] = source_name
    rows[0]["property_source_identity"] = "Synthetic test record"
    path = tmp_path / "source.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="verified provenance"):
        load_component_database(path)


@pytest.mark.parametrize(
    ("field", "placeholder"),
    [
        (field, placeholder)
        for field in ("property_source_identity", "citation_text")
        for placeholder in PROVENANCE_PLACEHOLDER_INPUTS
    ],
)
def test_verified_status_rejects_placeholder_free_text_evidence(
    tmp_path: Path, field: str, placeholder: str
) -> None:
    rows = _rows()
    rows[0]["source_status"] = "verified"
    rows[0]["source_reference_name"] = "Synthetic test-only source"
    _clear_traceability_evidence(rows[0])
    rows[0][field] = placeholder
    path = tmp_path / "source.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="verified provenance"):
        load_component_database(path)


@pytest.mark.parametrize("field", ["url", "doi"])
def test_verified_status_rejects_placeholder_structured_evidence(
    tmp_path: Path, field: str
) -> None:
    rows = _rows()
    rows[0]["source_status"] = "verified"
    rows[0]["source_reference_name"] = "Synthetic test-only source"
    rows[0][field] = "N/A"
    path = tmp_path / "source.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="verified provenance"):
        load_component_database(path)


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "example",
        "www.example.test/source",
        "://broken",
        "ftp://example.test/source",
        "http:///missing-host",
        "https://example.test:bad-port/source",
    ],
)
def test_verified_status_rejects_malformed_urls(tmp_path: Path, url: str) -> None:
    rows = _rows()
    rows[0]["source_status"] = "verified"
    rows[0]["source_reference_name"] = "Synthetic test-only source"
    rows[0]["url"] = url
    rows[0]["property_source_identity"] = "Otherwise valid test record"
    path = tmp_path / "source.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match=r"absolute HTTP\(S\) URL"):
        load_component_database(path)


@pytest.mark.parametrize(
    "doi",
    [
        "not-a-doi",
        "10.",
        "doi",
        "abc/123",
        "10.1234/",
        "10.12/test",
        "doi:10.1234/test",
        "https://doi.org/10.1234/test",
    ],
)
def test_verified_status_rejects_malformed_dois(tmp_path: Path, doi: str) -> None:
    rows = _rows()
    rows[0]["source_status"] = "verified"
    rows[0]["source_reference_name"] = "Synthetic test-only source"
    rows[0]["doi"] = doi
    rows[0]["property_source_identity"] = "Otherwise valid test record"
    path = tmp_path / "source.csv"
    _write_database(path, rows)
    with pytest.raises(ComponentDatabaseError, match="canonical 10.<registrant>"):
        load_component_database(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("property_source_identity", "Synthetic test record ID"),
        ("citation_text", "Synthetic test citation; not a production source"),
        ("url", "https://example.test/properties/methane-tc"),
        ("doi", "10.1234/test-only.synthetic-record"),
    ],
)
def test_valid_verified_property_accepts_one_traceability_mechanism(
    tmp_path: Path, field: str, value: str
) -> None:
    rows = _rows()
    rows[0]["source_status"] = "verified"
    rows[0]["source_reference_name"] = "  Synthetic test-only source  "
    _clear_traceability_evidence(rows[0])
    rows[0][field] = f"  {value}  "
    path = tmp_path / "source.csv"
    _write_database(path, rows)
    source = (
        load_component_database(path)
        .get_component("methane")
        .provenance.critical_temperature  # type: ignore[union-attr]
    )
    assert source.status is PropertySourceStatus.VERIFIED
    assert source.source_reference_name == "Synthetic test-only source"
    assert getattr(source, field) == value


def test_placeholder_matching_does_not_reject_legitimate_substrings(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[0]["source_status"] = "verified"
    rows[0]["source_reference_name"] = "Nonequilibrium Thermodynamics Handbook"
    rows[0]["property_source_identity"] = "Synthetic test record"
    path = tmp_path / "source.csv"
    _write_database(path, rows)
    source = (
        load_component_database(path)
        .get_component("methane")
        .provenance.critical_temperature  # type: ignore[union-attr]
    )
    assert source.status is PropertySourceStatus.VERIFIED


def _mixture(components: tuple, fractions: tuple[float, ...]) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(components, fractions, strict=True)
        )
    )


def test_database_components_preserve_pure_mixture_fugacity_and_order_mapping() -> None:
    database = load_component_database()
    methane = database.get_component("methane")
    propane = database.get_component("propane")
    forward = _mixture((methane, propane), (0.6, 0.4))
    reverse = _mixture((propane, methane), (0.4, 0.6))
    forward_parameters = calculate_peng_robinson_mixture_parameters(
        forward, 250.0, 3_000_000.0
    )
    reverse_parameters = calculate_peng_robinson_mixture_parameters(
        reverse, 250.0, 3_000_000.0
    )
    assert forward_parameters.a_alpha_mix == reverse_parameters.a_alpha_mix
    assert forward_parameters.b_mix == reverse_parameters.b_mix
    forward_root = max(
        calculate_compressibility_roots(
            forward_parameters.A_mix, forward_parameters.B_mix
        )
    )
    reverse_root = max(
        calculate_compressibility_roots(
            reverse_parameters.A_mix, reverse_parameters.B_mix
        )
    )
    forward_fugacity = calculate_mixture_fugacity_coefficients(
        forward_parameters, forward_root
    )
    reverse_fugacity = calculate_mixture_fugacity_coefficients(
        reverse_parameters, reverse_root
    )
    assert {
        item.component_name: item.log_fugacity_coefficient for item in forward_fugacity
    } == pytest.approx(
        {
            item.component_name: item.log_fugacity_coefficient
            for item in reverse_fugacity
        },
        abs=2e-15,
    )


@pytest.mark.parametrize(
    "kind", [SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT]
)
def test_methane_propane_reverse_order_preserves_saturation_results(
    kind: SaturationKind,
) -> None:
    database = load_component_database()
    methane = database.get_component("methane")
    propane = database.get_component("propane")
    forward = _mixture((methane, propane), (0.6, 0.4))
    reverse = _mixture((propane, methane), (0.4, 0.6))

    forward_result = calculate_saturation_pressure(forward, 250.0, kind)
    reverse_result = calculate_saturation_pressure(reverse, 250.0, kind)

    assert tuple(
        item.component.name for item in forward_result.feed_mixture.components
    ) == ("Methane", "Propane")
    assert tuple(
        item.component.name for item in reverse_result.feed_mixture.components
    ) == ("Propane", "Methane")
    assert forward_result.status is SaturationStatus.CONVERGED
    assert reverse_result.status is forward_result.status
    assert reverse_result.convergence_status is forward_result.convergence_status
    assert reverse_result.pressure_pa == pytest.approx(
        forward_result.pressure_pa, rel=2e-11
    )

    forward_names = tuple(
        item.component.name for item in forward_result.feed_mixture.components
    )
    reverse_names = tuple(
        item.component.name for item in reverse_result.feed_mixture.components
    )

    def mapped(names: tuple[str, ...], values: tuple[float, ...]) -> dict[str, float]:
        return dict(zip(names, values, strict=True))

    assert mapped(reverse_names, reverse_result.parent_composition) == pytest.approx(
        mapped(forward_names, forward_result.parent_composition), abs=2e-15
    )
    assert mapped(reverse_names, reverse_result.incipient_composition) == pytest.approx(
        mapped(forward_names, forward_result.incipient_composition),
        rel=2e-9,
        abs=2e-11,
    )
    assert mapped(reverse_names, reverse_result.k_values) == pytest.approx(
        mapped(forward_names, forward_result.k_values), rel=2e-9, abs=2e-11
    )
    assert forward_result.parent_phase is not None
    assert reverse_result.parent_phase is not None
    assert forward_result.incipient_phase is not None
    assert reverse_result.incipient_phase is not None
    assert reverse_result.parent_phase.selected_compressibility_factor == pytest.approx(
        forward_result.parent_phase.selected_compressibility_factor,
        rel=2e-10,
        abs=2e-12,
    )
    assert (
        reverse_result.incipient_phase.selected_compressibility_factor
        == pytest.approx(
            forward_result.incipient_phase.selected_compressibility_factor,
            rel=2e-10,
            abs=2e-12,
        )
    )


def test_database_components_preserve_flash_and_bubble_dew_results() -> None:
    database_mixture = _mixture(
        (
            load_component_database().get_component("methane"),
            load_component_database().get_component("ethane"),
        ),
        (0.5, 0.5),
    )
    legacy_mixture = _mixture((METHANE, ETHANE), (0.5, 0.5))
    assert calculate_two_phase_flash(
        database_mixture, 170.0, 100_000.0
    ) == calculate_two_phase_flash(legacy_mixture, 170.0, 100_000.0)
    for kind in SaturationKind:
        historical = calculate_saturation_pressure(database_mixture, 220.0, kind)
        reference = calculate_saturation_pressure(legacy_mixture, 220.0, kind)
        newton = calculate_saturation_pressure(
            database_mixture, 220.0, kind, saturation_newton_enabled=True
        )
        newton_reference = calculate_saturation_pressure(
            legacy_mixture, 220.0, kind, saturation_newton_enabled=True
        )
        assert historical == reference
        assert newton == newton_reference


def test_database_components_preserve_short_envelope_result() -> None:
    database_mixture = _mixture(
        (
            load_component_database().get_component("methane"),
            load_component_database().get_component("ethane"),
        ),
        (0.5, 0.5),
    )
    settings = EnvelopeContinuationSettings(
        target_temperature_k=205.0,
        initial_temperature_step_k=5.0,
        maximum_points=2,
        saturation_newton_enabled=True,
    )
    result = trace_phase_envelope_branch(
        database_mixture,
        EnvelopeBranchKind.BUBBLE,
        settings,
        start_temperature_k=200.0,
    )
    reference = trace_phase_envelope_branch(
        _mixture((METHANE, ETHANE), (0.5, 0.5)),
        EnvelopeBranchKind.BUBBLE,
        settings,
        start_temperature_k=200.0,
    )
    assert result == reference
