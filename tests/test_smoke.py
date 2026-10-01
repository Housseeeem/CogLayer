"""Smoke tests: verify the package imports and exposes a version string."""

import coglayer


def test_version_is_string() -> None:
    """The package exposes a version string."""
    assert isinstance(coglayer.__version__, str)


def test_version_is_semver() -> None:
    """The version string looks like semantic versioning (major.minor.patch)."""
    parts = coglayer.__version__.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()
