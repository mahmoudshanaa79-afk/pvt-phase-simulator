"""Non-blocking diagnostics for Peng-Robinson mixture calculations."""

from dataclasses import dataclass
from enum import StrEnum
from math import sqrt
from typing import Final

from pvt_phase_simulator.eos.mixing_rules import PengRobinsonMixtureParameters

# This is a project diagnostic band, not a universal physical threshold. It
# flags nominal component critical coordinates where cubic-root conditioning
# deserves extra scrutiny; validation and calculated results are unchanged.
NOMINAL_CRITICAL_RELATIVE_BAND: Final = 1e-3


class DiagnosticSeverity(StrEnum):
    """Severity of a non-blocking EOS diagnostic."""

    INFO = "info"
    WARNING = "warning"


class DiagnosticCategory(StrEnum):
    """Scientific area associated with a diagnostic."""

    NUMERICAL_CONDITIONING = "numerical_conditioning"
    MODEL_APPLICABILITY = "model_applicability"
    DATA_QUALITY = "data_quality"


@dataclass(frozen=True, slots=True)
class EOSDiagnostic:
    """Immutable machine-readable non-blocking diagnostic record."""

    code: str
    severity: DiagnosticSeverity
    category: DiagnosticCategory
    message: str
    value: float | None = None


def evaluate_mixture_eos_diagnostics(
    parameters: PengRobinsonMixtureParameters,
) -> tuple[EOSDiagnostic, ...]:
    """Return immutable advisories without changing validation or EOS results.

    Diagnostics neither clamp values nor establish phase stability. The input
    parameter object's documented SI/dimensionless units are retained in any
    reported numerical value.
    """

    diagnostics: list[EOSDiagnostic] = []
    if parameters.defaulted_binary_interaction_pairs:
        diagnostics.append(
            EOSDiagnostic(
                code="DEFAULTED_BINARY_INTERACTIONS",
                severity=DiagnosticSeverity.WARNING,
                category=DiagnosticCategory.DATA_QUALITY,
                message=(
                    "One or more binary interaction coefficients were omitted "
                    "and modelled as zero."
                ),
                value=float(len(parameters.defaulted_binary_interaction_pairs)),
            )
        )

    for component_parameter in parameters.component_parameters:
        component = component_parameter.component
        temperature_distance = abs(
            parameters.temperature_k / component.critical_temperature_k - 1.0
        )
        pressure_distance = abs(
            parameters.pressure_pa / component.critical_pressure_pa - 1.0
        )
        critical_distance = max(temperature_distance, pressure_distance)
        if critical_distance <= NOMINAL_CRITICAL_RELATIVE_BAND:
            diagnostics.append(
                EOSDiagnostic(
                    code="NEAR_NOMINAL_COMPONENT_CRITICAL_POINT",
                    severity=DiagnosticSeverity.INFO,
                    category=DiagnosticCategory.NUMERICAL_CONDITIONING,
                    message=(
                        f"{component.name} is within the project diagnostic "
                        "band of its nominal critical coordinates."
                    ),
                    value=critical_distance,
                )
            )

        alpha_base = 1.0 + component_parameter.kappa * (
            1.0 - sqrt(component_parameter.reduced_temperature)
        )
        if alpha_base <= 0.0:
            diagnostics.append(
                EOSDiagnostic(
                    code="ALPHA_CORRELATION_TURNING_REGION",
                    severity=DiagnosticSeverity.WARNING,
                    category=DiagnosticCategory.MODEL_APPLICABILITY,
                    message=(
                        f"{component.name} is beyond the zero crossing of the "
                        "standard Peng-Robinson alpha-correlation base."
                    ),
                    value=alpha_base,
                )
            )

    return tuple(diagnostics)
