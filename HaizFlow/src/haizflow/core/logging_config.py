import logging
import os
import sys

from haizflow.config import LOGS_DIR


def configure_app_logging() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(LOGS_DIR, "app.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    sys.excepthook = _handle_unhandled_exception


def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

