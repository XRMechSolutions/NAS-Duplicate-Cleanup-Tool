"""Logging infrastructure for DupliCleaner.

Provides configurable logging with file and console handlers.
Log files are stored in the user's AppData directory.
"""

import contextlib
import faulthandler
import logging
import os
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Module-level logger cache
_loggers: dict[str, logging.Logger] = {}
_initialized = False
_log_file_path: Path | None = None


def get_log_directory() -> Path:
    """Get the directory for log files.

    Returns:
        Path to log directory in user's AppData/Local/DupliCleaner/logs
    """
    override = os.environ.get("DUPLICLEANER_LOG_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "DupliCleaner"
    else:
        base = Path.home() / ".duplicleaner"

    log_dir = base / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    except (PermissionError, FileNotFoundError):
        fallback_base = Path.cwd() / ".duplicleaner"
        fallback = fallback_base / "logs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def setup_logging(
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_file_size: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """Initialize the logging system.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to write logs to a file
        log_to_console: Whether to write logs to console
        max_file_size: Maximum size of each log file before rotation
        backup_count: Number of backup log files to keep
    """
    global _initialized
    global _log_file_path

    if _initialized:
        return

    root_logger = logging.getLogger("duplicleaner")
    root_logger.setLevel(level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Log format
    detailed_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    simple_format = logging.Formatter(
        "%(levelname)-8s | %(message)s"
    )

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(simple_format)
        root_logger.addHandler(console_handler)

    if log_to_file:
        log_dir = get_log_directory()
        log_file = log_dir / f"duplicleaner_{datetime.now():%Y%m%d}.log"

        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding="utf-8"
            )
        except PermissionError:
            fallback_dir = Path.cwd() / ".duplicleaner" / "logs"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            log_file = fallback_dir / f"duplicleaner_{datetime.now():%Y%m%d}.log"
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding="utf-8"
            )

        file_handler.setLevel(logging.DEBUG)  # File gets everything
        file_handler.setFormatter(detailed_format)
        root_logger.addHandler(file_handler)
        _log_file_path = log_file

    _initialized = True
    root_logger.info("Logging initialized")
    _install_exception_hooks()


def _install_exception_hooks() -> None:
    """Capture unhandled exceptions (main + threads) to the log file."""
    if not _log_file_path:
        return
    try:
        # Keep the handle open for faulthandler output.
        log_handle = open(_log_file_path, "a", encoding="utf-8")  # noqa: SIM115
    except OSError:
        return

    with contextlib.suppress(Exception):
        faulthandler.enable(log_handle, all_threads=True)

    def _log_exception(exc_type, exc_value, exc_traceback) -> None:
        logger = logging.getLogger("duplicleaner")
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = _log_exception

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        logger = logging.getLogger("duplicleaner")
        logger.critical("Unhandled thread exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_excepthook


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance for the module
    """
    if name in _loggers:
        return _loggers[name]

    # Ensure logging is set up
    if not _initialized:
        setup_logging()

    # Create child logger under duplicleaner namespace
    logger_name = name if name.startswith("duplicleaner") else f"duplicleaner.{name}"

    logger = logging.getLogger(logger_name)
    _loggers[name] = logger
    return logger


def set_log_level(level: int) -> None:
    """Change the logging level at runtime.

    Args:
        level: New logging level
    """
    root_logger = logging.getLogger("duplicleaner")
    root_logger.setLevel(level)

    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
            handler.setLevel(level)


class LogContext:
    """Context manager for temporarily changing log level."""

    def __init__(self, level: int):
        self.level = level
        self.previous_level: int | None = None

    def __enter__(self) -> "LogContext":
        root_logger = logging.getLogger("duplicleaner")
        self.previous_level = root_logger.level
        root_logger.setLevel(self.level)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.previous_level is not None:
            root_logger = logging.getLogger("duplicleaner")
            root_logger.setLevel(self.previous_level)
