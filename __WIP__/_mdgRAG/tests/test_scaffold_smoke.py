"""
Scaffold Smoke Test — verify the scaffold boots without crashing.

This test confirms that:
    - RuntimeController can be instantiated
    - bootstrap() completes without error
    - The application entry point main() returns cleanly
"""

from src.core.runtime.runtime_controller import RuntimeController
from src.app import main


def test_runtime_controller_bootstrap() -> None:
    """RuntimeController.bootstrap() should complete without error."""
    controller = RuntimeController()
    controller.bootstrap()


def test_app_main_no_subcommand_returns_one() -> None:
    """main() with no subcommand should return 1 (print help)."""
    from unittest.mock import patch
    with patch("sys.argv", ["graph-manifold"]):
        result = main()
    assert result == 1, f"main() returned {result}, expected 1 (no subcommand)"
