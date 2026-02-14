"""Folder Watcher for DupliCleaner.

Monitors configured folders for new files using polling.
When new files are detected (after debounce), triggers scanning,
hashing, deduplication, and optional auto-organization.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from duplicleaner.utils.config import WatchFolderEntry, get_config, save_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WatchEvent:
    """Describes a batch of new files detected in a watched folder."""

    watch_path: str
    new_files: list[str]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class _FolderState:
    """Internal tracking state for a single watched folder."""

    entry: WatchFolderEntry
    # {path: (mtime, size)} snapshot of known files
    known_files: dict[str, tuple[float, int]] = field(default_factory=dict)
    pending_files: list[str] = field(default_factory=list)
    last_change_ts: float | None = None
    initialized: bool = False


class FolderWatcher:
    """Polling-based folder watcher that detects new files and triggers processing.

    Usage:
        watcher = FolderWatcher(
            on_new_files=my_handler,
            on_status=status_callback,
        )
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(
        self,
        on_new_files: Callable[[WatchEvent], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ):
        self._on_new_files = on_new_files
        self._on_status = on_status

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._states: dict[str, _FolderState] = {}
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the watcher thread."""
        if self.is_running:
            logger.warning("Folder watcher already running")
            return

        config = get_config()
        if not config.watch.global_enabled:
            logger.info("Folder watching is disabled")
            return

        if not config.watch.watch_folders:
            logger.info("No watch folders configured")
            return

        self._stop_event.clear()
        self._initialize_states()

        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="FolderWatcher",
        )
        self._thread.start()
        logger.info("Folder watcher started (%d folders)", len(self._states))
        if self._on_status:
            self._on_status(f"Folder watcher started ({len(self._states)} folders)")

    def stop(self) -> None:
        """Stop the watcher thread."""
        if not self.is_running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Folder watcher stopped")
        if self._on_status:
            self._on_status("Folder watcher stopped")

    def _initialize_states(self) -> None:
        """Build initial state for each enabled watch folder."""
        config = get_config()
        self._states.clear()

        for entry in config.watch.watch_folders:
            if not entry.enabled or not entry.path:
                continue
            if not os.path.isdir(entry.path):
                logger.warning("Watch folder not found: %s", entry.path)
                continue
            self._states[entry.path] = _FolderState(entry=entry)

    def _run(self) -> None:
        """Main polling loop."""
        # First pass: snapshot existing files without triggering events
        for state in self._states.values():
            state.known_files = self._snapshot_folder(state.entry.path)
            state.initialized = True

        # Use the shortest poll interval among all folders
        min_interval = min(
            (s.entry.poll_interval_seconds for s in self._states.values()),
            default=60,
        )
        min_interval = max(min_interval, 5)  # Floor at 5 seconds

        while not self._stop_event.is_set():
            now = time.time()

            for path, state in list(self._states.items()):
                if self._stop_event.is_set():
                    break

                if not os.path.isdir(path):
                    continue

                try:
                    self._poll_folder(state, now)
                except Exception as e:
                    logger.error("Error polling %s: %s", path, e)

            self._stop_event.wait(timeout=min_interval)

    def _poll_folder(self, state: _FolderState, now: float) -> None:
        """Check a single folder for new files."""
        current = self._snapshot_folder(state.entry.path)

        # Find new files (in current but not in known)
        new_paths = []
        for fpath, (mtime, size) in current.items():
            if fpath not in state.known_files:
                # Verify file is stable (not still being written)
                if self._is_file_stable(fpath, size):
                    new_paths.append(fpath)

        if new_paths:
            state.pending_files.extend(new_paths)
            state.last_change_ts = now
            logger.debug(
                "%d new files detected in %s (%d pending)",
                len(new_paths), state.entry.path, len(state.pending_files),
            )

        # Update known files with current snapshot
        state.known_files = current

        # Check if debounce period has elapsed
        if (
            state.pending_files
            and state.last_change_ts
            and (now - state.last_change_ts) >= state.entry.debounce_seconds
        ):
            self._flush_pending(state)

    def _flush_pending(self, state: _FolderState) -> None:
        """Process accumulated pending files for a folder."""
        pending = list(state.pending_files)
        state.pending_files.clear()
        state.last_change_ts = None

        if not pending:
            return

        # Filter out files that no longer exist
        existing = [p for p in pending if os.path.exists(p)]
        if not existing:
            return

        logger.info(
            "Processing %d new files from %s",
            len(existing), state.entry.path,
        )
        if self._on_status:
            self._on_status(
                f"New files detected: {len(existing)} in {os.path.basename(state.entry.path)}"
            )

        event = WatchEvent(
            watch_path=state.entry.path,
            new_files=existing,
        )

        if self._on_new_files:
            try:
                self._on_new_files(event)
            except Exception as e:
                logger.error("Error processing watch event for %s: %s", state.entry.path, e)

    @staticmethod
    def _snapshot_folder(folder_path: str) -> dict[str, tuple[float, int]]:
        """Take a snapshot of all files in a folder.

        Returns:
            Dict mapping file path to (mtime, size) tuple
        """
        snapshot = {}
        try:
            for entry in os.scandir(folder_path):
                if entry.is_file(follow_symlinks=False):
                    try:
                        st = entry.stat()
                        snapshot[entry.path] = (st.st_mtime, st.st_size)
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError) as e:
            logger.debug("Cannot scan %s: %s", folder_path, e)
        return snapshot

    @staticmethod
    def _is_file_stable(path: str, expected_size: int) -> bool:
        """Check if a file has finished writing (size is stable)."""
        try:
            current_size = os.path.getsize(path)
            return current_size == expected_size and current_size > 0
        except OSError:
            return False

    def get_pending_counts(self) -> dict[str, int]:
        """Get pending file counts per watched folder (for UI display)."""
        return {
            path: len(state.pending_files)
            for path, state in self._states.items()
        }

    def get_watched_folder_count(self) -> int:
        """Get number of actively watched folders."""
        return len(self._states)

    def add_watch_folder(self, entry: WatchFolderEntry) -> None:
        """Add a new watch folder at runtime."""
        if not entry.path or not os.path.isdir(entry.path):
            raise ValueError(f"Invalid path: {entry.path}")

        config = get_config()
        # Avoid duplicates
        for existing in config.watch.watch_folders:
            if os.path.normpath(existing.path) == os.path.normpath(entry.path):
                raise ValueError(f"Already watching: {entry.path}")

        config.watch.watch_folders.append(entry)
        save_config()

        # If running, add to live states
        if self.is_running and entry.enabled:
            state = _FolderState(entry=entry)
            state.known_files = self._snapshot_folder(entry.path)
            state.initialized = True
            self._states[entry.path] = state

    def remove_watch_folder(self, path: str) -> None:
        """Remove a watch folder at runtime."""
        config = get_config()
        normalized = os.path.normpath(path)
        config.watch.watch_folders = [
            wf for wf in config.watch.watch_folders
            if os.path.normpath(wf.path) != normalized
        ]
        save_config()

        # Remove from live states
        self._states.pop(path, None)
        self._states.pop(normalized, None)

    def toggle_folder(self, path: str, enabled: bool) -> None:
        """Enable/disable a watch folder."""
        config = get_config()
        normalized = os.path.normpath(path)
        for wf in config.watch.watch_folders:
            if os.path.normpath(wf.path) == normalized:
                wf.enabled = enabled
                break
        save_config()

        if not enabled:
            self._states.pop(path, None)
            self._states.pop(normalized, None)
        elif self.is_running:
            entry = next(
                (wf for wf in config.watch.watch_folders if os.path.normpath(wf.path) == normalized),
                None,
            )
            if entry:
                state = _FolderState(entry=entry)
                state.known_files = self._snapshot_folder(entry.path)
                state.initialized = True
                self._states[entry.path] = state
