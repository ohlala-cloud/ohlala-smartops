"""Tests for the main entry point."""

from ohlala_smartops.__main__ import main


def test_main_returns_zero() -> None:
    """Test that main function returns 0 (success exit code)."""
    result = main()
    assert result == 0


def test_main_is_callable() -> None:
    """Test that main function is callable."""
    assert callable(main)
