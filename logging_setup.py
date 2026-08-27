import logging
import sys
import time

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

_log = logging.getLogger(__name__)


def setup_logging(log_level: str) -> None:
    """
    Configure the root logger to emit to stdout with an ISO-8601 UTC formatter.

    Format: %(asctime)sZ %(levelname)s %(message)s
    The asctime uses UTC time (via converter = time.gmtime).
    If log_level is not a valid level name, logs a warning and falls back to INFO.
    """
    if log_level not in _VALID_LEVELS:
        level = logging.INFO
        emit_warning = True
    else:
        level = getattr(logging, log_level)
        emit_warning = False

    # Configure root logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime  # Use UTC time
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Remove existing handlers to avoid duplicate output
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    if emit_warning:
        logging.warning(
            "Invalid LOG_LEVEL %r; falling back to INFO. Valid levels: %s",
            log_level,
            ", ".join(sorted(_VALID_LEVELS)),
        )
