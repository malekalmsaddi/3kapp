"""Global logging configuration with colorized, concise output."""

import logging
import os
from termcolor import colored

# Custom logging formatter for colorful logs
class ColorFormatter(logging.Formatter):
    COLORS = {
        'INFO': 'cyan',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'magenta',
        'DEBUG': 'green'
    }

    def format(self, record):
        levelname_color = self.COLORS.get(record.levelname, 'white')
        log_message = super().format(record)
        return colored(log_message, levelname_color)

def setup_logger():
    """Configure root logger with level from ``LOG_LEVEL`` env var.

    Third-party loggers (e.g. ``twilio``) are clamped to ``WARNING`` to
    avoid noisy request dumps in normal operation.
    """
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Console handler with colorful output
    has_color_handler = any(
        isinstance(handler, logging.StreamHandler)
        and isinstance(getattr(handler, "formatter", None), ColorFormatter)
        for handler in logger.handlers
    )
    if not has_color_handler:
        console_handler = logging.StreamHandler()
        formatter = ColorFormatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # In debug mode let external-service loggers (twilio, httpx) through so their
    # HTTP traffic is visible.  werkzeug request logs stay at WARNING regardless
    # because they duplicate Gunicorn's access log and add noise.
    external_level = log_level if log_level <= logging.DEBUG else logging.WARNING
    logging.getLogger("twilio").setLevel(external_level)
    logging.getLogger("httpx").setLevel(external_level)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    return logger


# Set up the logger globally
logger = setup_logger()

