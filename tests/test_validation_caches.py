"""The P9 validation caches never skip a check that could fail.

A validation that succeeded is reused only for the very same immutable object
(component rows, row tuples), for a mapping that still holds exactly the same
key and value objects, or for a root with exactly the same float bits.
Anything else is validated again, and failures are never cached.
"""

from __future__ import annotations

import dataclasses

import pytest

from pvt_phase_simulator.eos import mixing_rules, peng_robinson
from pvt_phase_simulator.eos.mixing_rules import (
    calculate_mixture_a_alpha,
    calculate_pure_component_mixture_parameters,
    get_binary_interaction_coefficient,
    validate_component_parameter_provenance,
)
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_compressibility_roots,
    validate_compressibility_root,
)
from pvt_phase_simulator.fluid_models import ETHANE, METHANE, FluidMixture
from pvt_phase_simulator.fluid_models import MixtureComponent as Item


def _rows() -> tuple[mixing_rules.PureComponentMixtureParameters, ...]:
    mixture = FluidMixture((Item(METHANE, 0.5), Item(ETHANE, 0.5)))
    return tuple(
        calculate_pure_component_mixture_parameters(item, 250.0)
        for item in mixture.components
    )


def test_a_forged_copy_of_a_validated_row_is_still_rejected() -> None:
    rows = _rows()
    validate_component_parameter_provenance(rows, 250.0)  # now cached
    forged = dataclasses.replace(rows[0], alpha=rows[0].alpha * 1.001)
    with pytest.raises(ValueError, match="alpha is inconsistent"):
        validate_component_parameter_provenance((forged, rows[1]), 250.0)
    with pytest.raises(ValueError, match="alpha is inconsistent"):
        calculate_mixture_a_alpha((forged, rows[1]))


def test_the_same_rows_at_another_temperature_are_checked_again() -> None:
    rows = _rows()
    validate_component_parameter_provenance(rows, 250.0)
    with pytest.raises(ValueError, match="temperature_k is inconsistent"):
        validate_component_parameter_provenance(rows, 260.0)


def test_a_failed_validation_is_not_cached() -> None:
    rows = _rows()
    forged = (dataclasses.replace(rows[0], b=rows[0].b * 2.0), rows[1])
    for _ in range(2):
        with pytest.raises(ValueError, match="b is inconsistent"):
            validate_component_parameter_provenance(forged)


def test_a_mapping_changed_after_validation_is_validated_again() -> None:
    names = ("Methane", "Ethane")
    mapping = {names: 0.01, names[::-1]: 0.01}
    assert get_binary_interaction_coefficient(*names, mapping) == 0.01
    mapping[names[::-1]] = 0.02  # now asymmetric
    with pytest.raises(ValueError, match="symmetric binary interactions"):
        get_binary_interaction_coefficient(*names, mapping)
    mapping[names[::-1]] = 0.01
    mapping[names] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        get_binary_interaction_coefficient(*names, mapping)


def test_a_root_is_reused_only_with_identical_bits() -> None:
    A, B = 0.12, 0.02
    root = max(calculate_compressibility_roots(A, B))
    validate_compressibility_root(root, A, B)  # cached
    with pytest.raises(ValueError):
        validate_compressibility_root(root * 1.01, A, B)
    with pytest.raises(ValueError, match="greater than B"):
        validate_compressibility_root(B, A, B)
    # Non-float arguments take the uncached path and behave as before.
    with pytest.raises(ValueError, match="greater than B"):
        validate_compressibility_root(0, A, B)


def test_the_caches_stay_bounded() -> None:
    for index in range(mixing_rules._VALIDATION_CACHE_LIMIT + 10):
        rows = _rows()
        validate_component_parameter_provenance(rows, 250.0)
        del index
    assert len(mixing_rules._VALIDATED_ROWS) <= mixing_rules._VALIDATION_CACHE_LIMIT
    assert len(mixing_rules._VALIDATED_ROW_SETS) <= mixing_rules._VALIDATION_CACHE_LIMIT
    for index in range(peng_robinson._VALIDATED_ROOT_LIMIT + 10):
        A = 0.1 + index * 1e-9
        validate_compressibility_root(
            max(calculate_compressibility_roots(A, 0.02)), A, 0.02
        )
    assert len(peng_robinson._VALIDATED_ROOTS) <= peng_robinson._VALIDATED_ROOT_LIMIT
