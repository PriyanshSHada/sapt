"""
sapt.utils.logger
Centralized logging configuration for production observability.

Features:
- Console output (colored via rich)
- Structured logging
- Secret masking (API keys, tokens)
- Support for file logging (future)
"""

import logging
import sys
from pathlib import Path

from sapt.utils.constants import DATA_DIR


class SecretMaskingFormatter(logging.Formatter):
    """Formatter that masks sensitive information."""

    SENSITIVE_KEYS = {
        "api_key",
        "token",
        "password",
        "secret",
        "authorization",
        "x-api-key",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with secret masking."""
        msg = super().format(record)

        # Mask API keys in message
        for key in self.SENSITIVE_KEYS:
            if key in msg.lower():
                # Replace patterns like "api_key: sk-..."
                import re

                pattern = rf"{key}[:\s=]+[^\s,;]]*"
                msg = re.sub(
                    pattern,
                    f"{key}=***MASKED***",
                    msg,
                    flags=re.IGNORECASE,
                )

        return msg


def setup_logging(
    level: int = logging.INFO,
    enable_file: bool = False,
    log_file: Path | None = None,
) -> logging.Logger:
    """Configure root logger with console + optional file handlers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_file: Whether to enable file logging
        log_file: Path to log file (default: ~/.local/share/sapt/sapt.log)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("sapt")
    logger.setLevel(logging.DEBUG)  # Capture all; filter at handler level
    logger.propagate = False  # Don't propagate to root logger

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler (with masking)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_formatter = SecretMaskingFormatter(
        fmt="[%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (optional, for production deployments)
    if enable_file:
        log_file = log_file or (DATA_DIR / "sapt.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)  # Log everything to file
            file_formatter = SecretMaskingFormatter(
                fmt="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not enable file logging: {e}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(f"sapt.{name.split('.')[-1]}")
