"""Profiling helpers for DupliCleaner.

Provides lightweight wall-clock timing and optional cProfile capture.
"""

from __future__ import annotations

import cProfile
import logging
import os
import pstats
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from duplicleaner.utils.logging import get_log_directory

logger = logging.getLogger("duplicleaner.profiling")

_enabled = False
_min_ms = 0.0
_lock = threading.Lock()


@dataclass(frozen=True)
class CpuProfileSession:
    profiler: cProfile.Profile
    output_path: Path


def _env_truthy(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def configure_profiling(enabled: bool | None = None, min_ms: float | None = None) -> None:
    """Configure profiling behavior.

    Args:
        enabled: Enable timing output when True (defaults from env if None).
        min_ms: Minimum milliseconds to log timing (defaults from env if None).
    """
    global _enabled
    global _min_ms

    if enabled is None:
        enabled = _env_truthy("DUPLICLEANER_PROFILE")
    if min_ms is None:
        raw = os.environ.get("DUPLICLEANER_PROFILE_MIN_MS", "").strip()
        try:
            min_ms = float(raw) if raw else 0.0
        except ValueError:
            min_ms = 0.0

    _enabled = bool(enabled)
    _min_ms = float(min_ms)


def enable_profiling(min_ms: float = 0.0) -> None:
    """Enable lightweight timing output."""
    configure_profiling(enabled=True, min_ms=min_ms)


def disable_profiling() -> None:
    """Disable timing output."""
    configure_profiling(enabled=False, min_ms=0.0)


def is_enabled() -> bool:
    return _enabled


def get_min_ms() -> float:
    return _min_ms


@contextmanager
def profile_block(name: str, min_ms: float | None = None) -> Iterator[None]:
    """Context manager to time a block and log elapsed milliseconds."""
    if not _enabled:
        yield
        return

    threshold = _min_ms if min_ms is None else float(min_ms)
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms >= threshold:
            logger.info("profile %s: %.2f ms", name, elapsed_ms)


def _default_profile_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = get_log_directory()
    return log_dir / f"profile_{timestamp}.prof"


def start_cpu_profiler(output_path: str | Path | None = None) -> CpuProfileSession:
    """Start cProfile profiling and return the session."""
    if output_path is None:
        path = _default_profile_path()
    else:
        path = Path(output_path)
        if path.is_dir():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = path / f"profile_{timestamp}.prof"

    profiler = cProfile.Profile()
    profiler.enable()
    logger.info("CPU profiler started: %s", path)
    return CpuProfileSession(profiler=profiler, output_path=path)


def stop_cpu_profiler(
    session: CpuProfileSession | None,
    sort: str = "cumtime",
    top: int = 60,
) -> Path | None:
    """Stop cProfile session, write .prof and a text summary."""
    if session is None:
        return None

    with _lock:
        session.profiler.disable()
        session.output_path.parent.mkdir(parents=True, exist_ok=True)
        session.profiler.dump_stats(str(session.output_path))

        summary_path = session.output_path.with_suffix(".txt")
        with open(summary_path, "w", encoding="utf-8") as handle:
            stats = pstats.Stats(session.profiler, stream=handle)
            stats.strip_dirs().sort_stats(sort).print_stats(top)

    logger.info("CPU profiler written: %s (summary %s)", session.output_path, summary_path)
    return session.output_path


configure_profiling()
