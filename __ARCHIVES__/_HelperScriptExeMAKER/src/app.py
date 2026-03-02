#!/usr/bin/env python3
"""
app.py

Dumb interconnection layer between:
- engine.py (build pipeline orchestrator / CLI-capable)
- ui.py     (Tkinter wrapper around the engine)

Rules:
- Logging is configured ONCE here.
- engine remains usable as a CLI without UI.
- UI remains a thin wrapper that calls engine.build_exe(...).
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional


def configure_logging(verbose: bool = False) -> None:
    """Configure logging once for the entire application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_app_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse only the 'mode' args for the app.
    All build args are handled by engine.py when running in --cli mode.
    """
    p = argparse.ArgumentParser(
        prog="HelperScriptExeMAKER",
        add_help=True,
        description="HelperScriptExeMAKER - GUI wrapper + CLI entrypoint",
    )
    p.add_argument(
        "--cli",
        action="store_true",
        help="Run in CLI mode (delegates to engine.py argument parsing and execution).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG).",
    )
    return p.parse_args(argv)


def run_cli_passthrough() -> int:
    """
    Run engine's CLI as-is. We do not re-parse build args here.
    This keeps engine.py as the authoritative CLI interface.
    """
    # Package-safe import: works when invoked as `python -m src.app`
    try:
        from . import engine  # type: ignore
    except Exception:
        import engine  # type: ignore  # fallback for direct execution

    # engine.main() uses engine.parse_args() internally.
    return int(engine.main())


def run_gui() -> int:
    """
    Run Tkinter UI wrapper. UI should call engine.build_exe(...) under the hood.

    Rules:
    - When invoked as a module (python -m src.app), we MUST import as src.ui.
    - We do NOT fall back to top-level `import ui` in module mode, because that hides
      the real underlying import error (syntax error, missing dependency, etc.).
    - When executed as a script (no package), we import `ui` from the same directory.
    """
    log = logging.getLogger("app")

    try:
        if __package__:
            from . import ui as ui_mod  # type: ignore
        else:
            import ui as ui_mod  # type: ignore
    except Exception as e:
        log.error(
            "UI module failed to import. If ui.py is not implemented yet, use --cli. Error: %s",
            e,
        )
        return 2

    # Support either ui.run() or ui.main() as entrypoint
    if hasattr(ui_mod, "run"):
        ui_mod.run()
        return 0
    if hasattr(ui_mod, "main"):
        return int(ui_mod.main())

    log.error("ui.py has no run() or main() entrypoint.")
    return 2


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_app_args(argv)

    configure_logging(verbose=args.verbose)

    if args.cli:
        return run_cli_passthrough()

    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))




