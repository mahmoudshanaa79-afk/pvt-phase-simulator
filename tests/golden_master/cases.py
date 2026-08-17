"""Explicit, stable case definitions for the numerical golden master."""

from dataclasses import dataclass
from typing import Literal

from pvt_phase_simulator.fluid_models import ETHANE, METHANE, PROPANE, Component

CalculationType = Literal["pure_pr", "stability", "flash", "bubble", "dew", "envelope"]


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One explicit deterministic calculation request."""

    case_id: str
    calculation_type: CalculationType
    components: tuple[Component, ...]
    composition: tuple[float, ...]
    temperature_k: float
    pressure_pa: float | None = None
    target_temperature_k: float | None = None
    temperature_step_k: float | None = None
    maximum_points: int = 8
    envelope_kind: Literal["bubble", "dew"] | None = None
    envelope_variant: str | None = None


COMPONENT_SLUGS = {METHANE: "methane", ETHANE: "ethane", PROPANE: "propane"}
PURE_TEMPERATURES = (130.0, 150.0, 180.0, 190.56, 220.0, 300.0, 400.0)
PURE_PRESSURES = (
    10_000.0,
    100_000.0,
    500_000.0,
    1_000_000.0,
    3_000_000.0,
    5_000_000.0,
    10_000_000.0,
    30_000_000.0,
)

MIXTURES: tuple[tuple[str, tuple[Component, ...], tuple[float, ...]], ...] = (
    ("ch4_c2_20_80", (METHANE, ETHANE), (0.2, 0.8)),
    ("ch4_c2_50_50", (METHANE, ETHANE), (0.5, 0.5)),
    ("ch4_c2_80_20", (METHANE, ETHANE), (0.8, 0.2)),
    ("ch4_c3_20_80", (METHANE, PROPANE), (0.2, 0.8)),
    ("ch4_c3_50_50", (METHANE, PROPANE), (0.5, 0.5)),
    ("ch4_c3_60_40", (METHANE, PROPANE), (0.6, 0.4)),
    ("ch4_c3_80_20", (METHANE, PROPANE), (0.8, 0.2)),
    ("ch4_c2_c3_60_30_10", (METHANE, ETHANE, PROPANE), (0.6, 0.3, 0.1)),
    ("ch4_c2_c3_40_40_20", (METHANE, ETHANE, PROPANE), (0.4, 0.4, 0.2)),
    ("ch4_c2_c3_80_10_10", (METHANE, ETHANE, PROPANE), (0.8, 0.1, 0.1)),
)

SPECIAL_MIXTURES: tuple[tuple[str, tuple[Component, ...], tuple[float, ...]], ...] = (
    ("ch4_c2_20_80_reversed", (ETHANE, METHANE), (0.8, 0.2)),
    ("ch4_c2_50_50_reversed", (ETHANE, METHANE), (0.5, 0.5)),
    ("ch4_c3_60_40_reversed", (PROPANE, METHANE), (0.4, 0.6)),
    (
        "ch4_c2_c3_60_30_10_reversed",
        (PROPANE, ETHANE, METHANE),
        (0.1, 0.3, 0.6),
    ),
    ("ch4_c2_c3_zero_c3", (METHANE, ETHANE, PROPANE), (0.5, 0.5, 0.0)),
    ("ch4_c2_c3_zero_c2", (METHANE, ETHANE, PROPANE), (0.6, 0.0, 0.4)),
    ("ch4_c2_c3_zero_ch4", (METHANE, ETHANE, PROPANE), (0.0, 0.5, 0.5)),
    ("ch4_c2_near_pure_ch4", (METHANE, ETHANE), (0.999999, 0.000001)),
    ("ch4_c2_near_pure_c2", (METHANE, ETHANE), (0.000001, 0.999999)),
    ("ch4_c3_near_pure_ch4", (METHANE, PROPANE), (0.999999, 0.000001)),
    ("ch4_c3_near_pure_c3", (METHANE, PROPANE), (0.000001, 0.999999)),
)


def _temperature_slug(value: float) -> str:
    return f"{value:g}".replace(".", "p") + "k"


def _pressure_slug(value: float) -> str:
    return f"{value / 1_000_000:g}".replace(".", "p") + "mpa"


def build_cases() -> tuple[GoldenCase, ...]:
    """Return the complete explicit matrix in stable case-ID order."""

    cases: list[GoldenCase] = []
    for component in (METHANE, ETHANE, PROPANE):
        name = COMPONENT_SLUGS[component]
        for temperature in PURE_TEMPERATURES:
            for pressure in PURE_PRESSURES:
                cases.append(
                    GoldenCase(
                        f"pure_{name}_{_temperature_slug(temperature)}_"
                        f"{_pressure_slug(pressure)}",
                        "pure_pr",
                        (component,),
                        (1.0,),
                        temperature,
                        pressure,
                    )
                )

    for slug, components, composition in MIXTURES:
        for temperature in (180.0, 250.0):
            for pressure in (500_000.0, 5_000_000.0):
                suffix = f"{_temperature_slug(temperature)}_{_pressure_slug(pressure)}"
                for calculation_type in ("stability", "flash"):
                    cases.append(
                        GoldenCase(
                            f"{calculation_type}_{slug}_{suffix}",
                            calculation_type,
                            components,
                            composition,
                            temperature,
                            pressure,
                        )
                    )
        for temperature in (180.0, 250.0):
            for kind in ("bubble", "dew"):
                cases.append(
                    GoldenCase(
                        f"{kind}_{slug}_{_temperature_slug(temperature)}",
                        kind,
                        components,
                        composition,
                        temperature,
                    )
                )

    for slug, components, composition in SPECIAL_MIXTURES:
        for calculation_type in ("stability", "flash"):
            cases.append(
                GoldenCase(
                    f"{calculation_type}_{slug}_250k_2mpa",
                    calculation_type,
                    components,
                    composition,
                    250.0,
                    2_000_000.0,
                )
            )

    # Required physical dew regression, kept separate and semantically pinned.
    cases.append(
        GoldenCase(
            "dew_ch4_c3_60_40_250k_physical_branch",
            "dew",
            (METHANE, PROPANE),
            (0.6, 0.4),
            250.0,
        )
    )

    envelope_specs = (
        (
            "bubble_ch4_c2_forward_200_220",
            "bubble",
            MIXTURES[1],
            200.0,
            220.0,
            5.0,
            8,
            "ordinary",
        ),
        (
            "dew_ch4_c2_forward_200_220",
            "dew",
            MIXTURES[1],
            200.0,
            220.0,
            5.0,
            8,
            "ordinary",
        ),
        (
            "bubble_ch4_c2_reverse_210_200",
            "bubble",
            MIXTURES[1],
            210.0,
            200.0,
            -5.0,
            6,
            "ordinary",
        ),
        (
            "bubble_ch4_c3_forward_230_250",
            "bubble",
            MIXTURES[5],
            230.0,
            250.0,
            5.0,
            8,
            "ordinary",
        ),
        (
            "dew_ch4_c3_forward_230_250",
            "dew",
            MIXTURES[5],
            230.0,
            250.0,
            5.0,
            8,
            "ordinary",
        ),
        (
            "bubble_ternary_forward_200_220",
            "bubble",
            MIXTURES[7],
            200.0,
            220.0,
            5.0,
            8,
            "ordinary",
        ),
        (
            "dew_ternary_forward_200_220",
            "dew",
            MIXTURES[7],
            200.0,
            220.0,
            5.0,
            8,
            "ordinary",
        ),
        (
            "bubble_pure_methane_forward_150_170",
            "bubble",
            ("pure", (METHANE,), (1.0,)),
            150.0,
            170.0,
            5.0,
            8,
            "ordinary",
        ),
        (
            "dew_pure_methane_reverse_170_150",
            "dew",
            ("pure", (METHANE,), (1.0,)),
            170.0,
            150.0,
            -5.0,
            8,
            "ordinary",
        ),
        (
            "continuation_only_ch4_c2_bubble_240_250",
            "bubble",
            MIXTURES[1],
            240.0,
            250.0,
            5.0,
            6,
            "ordinary",
        ),
        (
            "continuation_only_ternary_bubble_220_230",
            "bubble",
            MIXTURES[7],
            220.0,
            230.0,
            5.0,
            6,
            "ordinary",
        ),
        (
            "bubble_pure_methane_near_critical",
            "bubble",
            ("pure", (METHANE,), (1.0,)),
            150.0,
            175.0,
            5.0,
            8,
            "near_critical",
        ),
        (
            "bubble_ch4_c2_maximum_points",
            "bubble",
            MIXTURES[1],
            200.0,
            240.0,
            5.0,
            2,
            "ordinary",
        ),
        (
            "bubble_ch4_c2_pressure_out_of_bounds",
            "bubble",
            MIXTURES[1],
            200.0,
            220.0,
            5.0,
            8,
            "pressure_bounds",
        ),
        (
            "bubble_ch4_c2_branch_lost",
            "bubble",
            MIXTURES[1],
            200.0,
            205.0,
            5.0,
            5,
            "branch_lost",
        ),
        (
            "bubble_ch4_c2_minimum_step_reached",
            "bubble",
            MIXTURES[1],
            200.0,
            205.0,
            5.0,
            6,
            "minimum_step",
        ),
        (
            "bubble_ch4_c2_corrector_failed",
            "bubble",
            MIXTURES[1],
            200.0,
            201.0,
            1.0,
            2,
            "corrector_failed",
        ),
    )
    for case_id, kind, mixture, start, target, step, maximum, variant in envelope_specs:
        _, components, composition = mixture
        cases.append(
            GoldenCase(
                case_id,
                "envelope",
                components,
                composition,
                start,
                target_temperature_k=target,
                temperature_step_k=step,
                maximum_points=maximum,
                envelope_kind=kind,
                envelope_variant=variant,
            )
        )

    ordered = tuple(sorted(cases, key=lambda item: item.case_id))
    validate_case_ids(ordered)
    return ordered


def validate_case_ids(cases: tuple[GoldenCase, ...]) -> None:
    """Reject empty or duplicate stable identifiers."""

    identifiers = [case.case_id for case in cases]
    if any(not item or item.strip() != item for item in identifiers):
        raise ValueError(
            "case IDs must be non-empty and have no surrounding whitespace"
        )
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate case IDs: {', '.join(duplicates)}")
