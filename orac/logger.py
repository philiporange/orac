"""
Centralized logging configuration using loguru.
"""

import sys
from loguru import logger
from orac.config import Config

# Remove default handler
logger.remove()

# Add file handler (always active)
log_file = Config.LOG_FILE
logger.add(
    log_file,
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    format=(
        "{time:YYYY-MM-DD HH:mm:ss} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    ),
)


def configure_console_logging(verbose: bool = False):
    """
    Configure console logging based on verbose setting.

    Args:
    verbose: If True, show INFO and above on console.
        If False, suppress all console output.
    """
    # Remove any existing console handlers
    logger.remove()

    # Re-add file handler
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
    )

    # Add console handler only in verbose mode
    if verbose:
        logger.add(
            sys.stderr,
            level="INFO",
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:"
                "<cyan>{function}</cyan>:"
                "<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
        )
    # In non-verbose mode,
    # no console handler is added,
    # so no loguru messages go to stdout/stderr


# Default configuration (non-verbose)
configure_console_logging(verbose=False)
