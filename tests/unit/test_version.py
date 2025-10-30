"""Tests for version module."""

from ohlala_smartops.version import __version__, get_version


def test_version_string_format() -> None:
    """Test that version string follows semantic versioning."""
    assert isinstance(__version__, str)
    assert len(__version__.split(".")) == 3  # Major.Minor.Patch


def test_get_version_returns_string() -> None:
    """Test that get_version returns the version string."""
    version = get_version()
    assert isinstance(version, str)
    assert version == __version__


def test_version_matches_expected() -> None:
    """Test that version matches expected value."""
    assert __version__ == "0.1.0"
