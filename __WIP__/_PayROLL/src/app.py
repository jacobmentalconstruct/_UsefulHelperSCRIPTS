from __future__ import annotations

import logging
from pathlib import Path
import sys

from orchestration import ApplicationOrchestrator


def configure_logging(workspace_root: Path) -> None:
    log_dir = workspace_root / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "payroll_app.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    workspace_root = Path(__file__).resolve().parent.parent
    configure_logging(workspace_root)
    logger = logging.getLogger("payroll.bootstrap")
    app = ApplicationOrchestrator(workspace_root)

    def handle_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
        logger.exception("Unhandled application exception", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            app.handle_ui_exception(exc_type, exc_value, exc_traceback)
        except Exception:
            logger.exception("Failed while handling unhandled exception")
            raise

    sys.excepthook = handle_unhandled_exception
    logger.info("Starting payroll prototype")
    app.start()


if __name__ == "__main__":
    main()
