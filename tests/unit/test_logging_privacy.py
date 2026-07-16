import logging

from app.logging_config import configure_logging


def test_url_bearing_transport_loggers_are_suppressed() -> None:
    configure_logging("INFO")
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.CRITICAL
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.CRITICAL
