import logging
from typing import TextIO


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    log_level: str,
    *,
    logger_name: str = "app",
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure and return a dedicated application logger."""
    try:
        level = logging._nameToLevel[log_level.upper()]
    except KeyError as exc:
        valid_levels = ", ".join(logging._nameToLevel)
        raise ValueError(
            f"Unsupported log level {log_level!r}. Expected one of: {valid_levels}"
        ) from exc

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    )
    logger.addHandler(handler)

    return logger
