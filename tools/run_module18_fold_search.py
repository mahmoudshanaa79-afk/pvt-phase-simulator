"""Reproduce the bounded Module 18 physical turning-point search."""

from pvt_phase_simulator.eos.phase_envelope import EnvelopeBranchKind
from pvt_phase_simulator.eos.pseudo_arclength import (
    PseudoArclengthSettings,
    trace_pseudo_arclength_branch,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)


def _binary(heavy: Component, methane_fraction: float) -> FluidMixture:
    return FluidMixture(
        (
            MixtureComponent(METHANE, methane_fraction),
            MixtureComponent(heavy, 1.0 - methane_fraction),
        )
    )


def main() -> None:
    """Print deterministic zero-kij search summaries; do not mutate artifacts."""

    cases: list[tuple[str, FluidMixture, float]] = []
    for heavy, name, start in ((ETHANE, "ch4_c2", 180.0), (PROPANE, "ch4_c3", 210.0)):
        for methane_fraction in (0.2, 0.5, 0.8):
            cases.append(
                (
                    f"{name}_{methane_fraction:.1f}",
                    _binary(heavy, methane_fraction),
                    start,
                )
            )
    cases.extend(
        (
            (
                "ternary_0.6_0.3_0.1",
                FluidMixture(
                    (
                        MixtureComponent(METHANE, 0.6),
                        MixtureComponent(ETHANE, 0.3),
                        MixtureComponent(PROPANE, 0.1),
                    )
                ),
                190.0,
            ),
            (
                "ternary_0.3_0.3_0.4",
                FluidMixture(
                    (
                        MixtureComponent(METHANE, 0.3),
                        MixtureComponent(ETHANE, 0.3),
                        MixtureComponent(PROPANE, 0.4),
                    )
                ),
                210.0,
            ),
        )
    )
    for name, mixture, start_temperature_k in cases:
        for branch_kind in EnvelopeBranchKind:
            for initial_temperature_step_k in (2.0, -2.0):
                result = trace_pseudo_arclength_branch(
                    mixture,
                    branch_kind,
                    PseudoArclengthSettings(
                        initial_temperature_step_k=initial_temperature_step_k,
                        initial_arclength_step=0.04,
                        maximum_arclength_step=0.08,
                        maximum_points=25,
                    ),
                    start_temperature_k,
                )
                temperatures = tuple(point.temperature_k for point in result.points)
                pressures = tuple(point.pressure_pa for point in result.points)
                print(
                    name,
                    branch_kind.value,
                    "up" if initial_temperature_step_k > 0.0 else "down",
                    result.termination_reason.value,
                    len(result.points),
                    result.temperature_turning_point_count,
                    result.pressure_turning_point_count,
                    min(temperatures) if temperatures else None,
                    max(temperatures) if temperatures else None,
                    min(pressures) if pressures else None,
                    max(pressures) if pressures else None,
                    result.rejected_steps,
                )


if __name__ == "__main__":
    main()
