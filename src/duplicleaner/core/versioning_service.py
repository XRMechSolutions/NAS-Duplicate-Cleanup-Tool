"""Background service for version tracking.

Watches tracked folders and commits changes to local Git repos.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as dt_time
from pathlib import Path

from duplicleaner.core.versioning import VersionTracker
from duplicleaner.utils.config import VersioningSettings
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TrackedRepoState:
    """Runtime state for a tracked repository."""
    tracker: VersionTracker
    last_snapshot: dict[str, tuple[float, int]] = field(default_factory=dict)
    pending_paths: set[str] = field(default_factory=set)
    last_change_ts: float | None = None
    last_daily_commit_date: str | None = None


class VersioningService:
    """Monitors tracked folders and auto-commits changes locally."""

    def __init__(
        self,
        settings: VersioningSettings,
        poll_interval_seconds: int = 5,
        debounce_seconds: int = 60,
    ) -> None:
        self.settings = settings
        self.poll_interval_seconds = max(1, poll_interval_seconds)
        self.debounce_seconds = max(5, debounce_seconds)

        self._repos: dict[str, TrackedRepoState] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start background monitoring."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._initialize_repos()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Versioning service started")

    def stop(self, timeout: float = 2.0) -> None:
        """Stop background monitoring."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("Versioning service stopped")

    def refresh_tracked_folders(self) -> None:
        """Refresh tracked folders based on settings."""
        self._initialize_repos()

    def _initialize_repos(self) -> None:
        """Initialize tracker instances for configured folders."""
        tracked = set(self.settings.tracked_folders)

        # Remove deleted
        for path in list(self._repos.keys()):
            if path not in tracked:
                self._repos.pop(path, None)

        for folder in tracked:
            if folder in self._repos:
                continue

            tracker = VersionTracker(
                root_path=folder,
                include_patterns=self.settings.include_patterns or None,
                exclude_patterns=self.settings.exclude_patterns,
                include_subfolders=self.settings.include_subfolders,
                max_file_size_mb=self.settings.max_file_size_mb,
            )

            if not tracker.is_available():
                logger.warning("Versioning disabled: GitPython not available")
                return

            if tracker.init_repository():
                tracker.initial_commit()
                state = TrackedRepoState(tracker=tracker)
                state.last_snapshot = self._snapshot_files(tracker)
                self._repos[folder] = state

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as exc:
                logger.error(f"Versioning service error: {exc}")
            time.sleep(self.poll_interval_seconds)

    def _poll(self) -> None:
        mode = self.settings.auto_commit_mode
        for state in self._repos.values():
            if mode == "manual":
                continue

            if mode == "interval":
                self._commit_interval(state)
                continue

            if mode == "daily":
                self._commit_daily(state)
                continue

            # Default: on_save (watch for changes)
            self._detect_and_commit(state)

    def _detect_and_commit(self, state: TrackedRepoState) -> None:
        snapshot = self._snapshot_files(state.tracker)
        changed = self._diff_snapshot(state.last_snapshot, snapshot)

        if changed:
            state.pending_paths.update(changed)
            state.last_change_ts = time.time()

        state.last_snapshot = snapshot

        if not state.pending_paths or state.last_change_ts is None:
            return

        if time.time() - state.last_change_ts < self.debounce_seconds:
            return

        message = self._build_commit_message(state.pending_paths)
        committed = state.tracker.commit_all(message)
        if committed:
            logger.info(message)

        state.pending_paths.clear()
        state.last_change_ts = None

    def _commit_interval(self, state: TrackedRepoState) -> None:
        minutes = max(1, self.settings.auto_commit_interval_minutes)
        now = time.time()

        if state.last_change_ts is None:
            state.last_change_ts = now
            return

        if now - state.last_change_ts < minutes * 60:
            return

        committed = state.tracker.commit_all("Auto-save: interval commit")
        if committed:
            logger.info("Auto-save: interval commit")

        state.last_change_ts = now

    def _commit_daily(self, state: TrackedRepoState) -> None:
        daily_time = self._parse_daily_time(self.settings.auto_commit_daily_time)
        now = datetime.now()
        today_key = now.strftime("%Y-%m-%d")

        if state.last_daily_commit_date == today_key:
            return

        if now.time() < daily_time:
            return

        committed = state.tracker.commit_all("Auto-save: daily commit")
        if committed:
            logger.info("Auto-save: daily commit")

        state.last_daily_commit_date = today_key

    def _parse_daily_time(self, value: str) -> dt_time:
        try:
            parts = value.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            return dt_time(hour=hour, minute=minute)
        except Exception:
            return dt_time(hour=0, minute=0)

    def _snapshot_files(self, tracker: VersionTracker) -> dict[str, tuple[float, int]]:
        snapshot: dict[str, tuple[float, int]] = {}
        for path in tracker.list_tracked_files():
            try:
                stat = path.stat()
                snapshot[str(path)] = (stat.st_mtime, stat.st_size)
            except OSError:
                continue
        return snapshot

    def _diff_snapshot(
        self,
        old: dict[str, tuple[float, int]],
        new: dict[str, tuple[float, int]],
    ) -> set[str]:
        changed: set[str] = set()

        for path, meta in new.items():
            if path not in old:
                changed.add(path)
                continue
            if old[path] != meta:
                changed.add(path)

        for path in old:
            if path not in new:
                changed.add(path)

        return changed

    def _build_commit_message(self, paths: set[str]) -> str:
        count = len(paths)
        if count == 1:
            item = Path(next(iter(paths))).name
            return f"Auto-save: {item}"
        return f"Auto-save: {count} files updated"
