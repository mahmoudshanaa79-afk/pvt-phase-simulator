"""Data-encoded metric policy; model accuracy is descriptive and never gates CI."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from .enums import ValidationQuantity


class MetricState(StrEnum):
    DEFINED = "DEFINED"
    UNDEFINED = "UNDEFINED"


class MetricName(StrEnum):
    MAE = "MAE"
    BIAS = "BIAS"
    RMSE = "RMSE"
    MAX_ABS_ERROR = "MAX_ABS_ERROR"
    AARD_PERCENT = "AARD_PERCENT"
    BIAS_PERCENT = "BIAS_PERCENT"
    RMS_RELATIVE_PERCENT = "RMS_RELATIVE_PERCENT"
    MAX_ABS_RELATIVE_PERCENT = "MAX_ABS_RELATIVE_PERCENT"


@dataclass(frozen=True, slots=True)
class MetricPolicy:
    per_observation: tuple[str, ...]
    primary: tuple[MetricName, ...]
    enabled: tuple[MetricName, ...]
    disabled: tuple[MetricName, ...]
    statement: str = "Equal weight per declared observation."


def _policy(
    per_observation: tuple[str, ...],
    primary: tuple[MetricName, ...],
    enabled: tuple[MetricName, ...],
    statement: str = "Equal weight per declared observation.",
) -> MetricPolicy:
    return MetricPolicy(
        per_observation,
        primary,
        enabled,
        tuple(m for m in MetricName if m not in enabled),
        statement,
    )


M = MetricName
_ABS = (M.MAE, M.BIAS, M.RMSE, M.MAX_ABS_ERROR)
METRIC_POLICY = MappingProxyType(
    {
        ValidationQuantity.PRESSURE: _policy(
            (
                "error",
                "absolute_error",
                "relative",
                "absolute_relative",
                "normalized_residual",
            ),
            (M.AARD_PERCENT, M.BIAS_PERCENT, M.MAE),
            (
                M.MAE,
                M.BIAS,
                M.RMSE,
                M.AARD_PERCENT,
                M.BIAS_PERCENT,
                M.RMS_RELATIVE_PERCENT,
                M.MAX_ABS_RELATIVE_PERCENT,
            ),
        ),
        ValidationQuantity.TEMPERATURE: _policy(
            ("error", "absolute_error"), (M.MAE, M.BIAS), _ABS
        ),
        ValidationQuantity.MOLE_FRACTION: _policy(
            ("error", "absolute_error"), (M.MAE, M.MAX_ABS_ERROR), _ABS
        ),
        ValidationQuantity.VAPOR_FRACTION: _policy(
            ("error", "absolute_error"),
            (M.MAE, M.MAX_ABS_ERROR),
            _ABS,
            "A predicted/reference phase-state mismatch is a classification "
            "disagreement, never a small numeric error.",
        ),
        ValidationQuantity.COMPRESSIBILITY_FACTOR: _policy(
            ("error", "absolute_error", "relative", "absolute_relative"),
            (M.AARD_PERCENT, M.MAE),
            (*_ABS, M.AARD_PERCENT, M.BIAS_PERCENT),
        ),
        ValidationQuantity.DENSITY: _policy(
            ("error", "absolute_error", "relative"),
            (M.AARD_PERCENT, M.MAE),
            (M.MAE, M.AARD_PERCENT, M.BIAS_PERCENT, M.MAX_ABS_ERROR),
        ),
    }
)
