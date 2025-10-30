"""Ohlala SmartOps main entry point."""

import sys

from ohlala_smartops.version import __version__


def main() -> int:
    """Main entry point for the application.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    print("Ohlala SmartOps - AI-powered AWS EC2 management bot")
    print(f"Version: {__version__}")
    print()
    print("This is the main entry point. Full implementation coming soon.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
