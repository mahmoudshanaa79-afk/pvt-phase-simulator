"""SHA-256 syntax and supplied-content verification helpers."""

from __future__ import annotations

import hashlib
import re

from .exceptions import HashMismatchError

_SHA256_PATTERN = re.compile(r"^[0-9A-Fa-f]{64}$")


def normalize_sha256(value: str) -> str:
    """Validate a SHA-256 digest and return its canonical uppercase form."""

    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(
            "SHA-256 digest must contain exactly 64 hexadecimal characters"
        )
    return value.upper()


def verify_sha256(content: bytes | str, expected_sha256: str) -> None:
    """Verify supplied bytes or UTF-8 text against an expected SHA-256 digest.

    This helper never reads a path. Constructing a provenance object validates only
    digest syntax; callers with actual normalized content must invoke this function.
    """

    expected = normalize_sha256(expected_sha256)
    supplied = content.encode("utf-8") if isinstance(content, str) else content
    if not isinstance(supplied, bytes):
        raise TypeError("content must be bytes or text")
    actual = hashlib.sha256(supplied).hexdigest().upper()
    if actual != expected:
        raise HashMismatchError(
            f"supplied content SHA-256 {actual} does not match expected {expected}"
        )
