"""Shared deterministic configuration for the test suite."""

from hypothesis import settings

settings.register_profile(
    "deterministic",
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
settings.load_profile("deterministic")
