import logging

from backend.app.core.config import get_settings


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, get_settings().log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
