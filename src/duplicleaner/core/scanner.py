"""File Scanner for DupliCleaner.

Recursively walks directories, collects file metadata, and stores
results in the database. Supports UNC paths, pause/resume, and
progress callbacks.
"""

import contextlib
import mimetypes
import os
import stat
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import Drive, FileRecord
from duplicleaner.utils.config import get_config
from duplicleaner.utils.logging import get_logger
from duplicleaner.utils.profiling import profile_block

logger = get_logger(__name__)


class ScanMode(Enum):
    """Type of scan to perform."""

    QUICK = "quick"   # Check mtime only, skip unchanged files
    DEEP = "deep"     # Re-examine all files regardless of mtime
    FULL = "full"     # Deep scan + AI analysis


class ScanState(Enum):
    """Current state of the scanner."""

    IDLE = "idle"
    SCANNING = "scanning"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ScanProgress:
    """Progress information for a scan."""

    files_found: int = 0
    folders_processed: int = 0
    files_new: int = 0
    files_modified: int = 0
    files_unchanged: int = 0
    files_removed: int = 0
    errors: int = 0
    current_path: str = ""
    start_time: datetime | None = None
    elapsed_seconds: float = 0.0
    files_per_second: float = 0.0
    state: ScanState = ScanState.IDLE

    # Error tracking
    permission_errors: int = 0
    path_too_long_errors: int = 0
    other_errors: int = 0
    error_paths: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    """Result of a completed scan."""

    drive_id: str
    total_files: int
    new_files: int
    modified_files: int
    removed_files: int
    errors: int
    duration_seconds: float
    error_paths: list[str]


# Default patterns to ignore
DEFAULT_IGNORE_PATTERNS = {
    # System folders
    "$RECYCLE.BIN",
    "System Volume Information",
    "Recovery",
    "$Recycle.Bin",

    # Windows system
    "Windows",
    "ProgramData",
    "Program Files",
    "Program Files (x86)",

    # Development
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".venv",
    "venv",
    ".env",
    "env",
    "dist",
    "build",
    "*.egg-info",

    # IDE
    ".idea",
    ".vscode",
    ".vs",

    # Temp files
    "Thumbs.db",
    "desktop.ini",
    ".DS_Store",
    "*.tmp",
    "*.temp",
    "~*",
    "*.bak",
}


class Scanner:
    """File system scanner with progress tracking and pause/resume support."""

    def __init__(
        self,
        db: Database | None = None,
        batch_size: int = 1000,
        progress_callback: Callable[[ScanProgress], None] | None = None,
    ):
        """Initialize the scanner.

        Args:
            db: Database instance (uses singleton if not provided)
            batch_size: Number of files to batch before database write
            progress_callback: Function called with progress updates
        """
        self.db = db or get_database()
        self.config = get_config()
        self.batch_size = batch_size
        self.progress_callback = progress_callback

        self._state = ScanState.IDLE
        self._progress = ScanProgress()
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._cancel_event = threading.Event()

        # Current batch for database writes
        self._file_batch: list[FileRecord] = []

        # Track seen files for removal detection
        self._seen_file_ids: set[int] = set()

        # Resume scan state
        self._scan_drive_id: str | None = None
        self._scan_mode: ScanMode | None = None
        self._scan_root: str | None = None
        self._resume_path: str | None = None
        self._resume_active = False
        self._resume_reached = False
        self._scan_started_at: datetime | None = None
        self._last_state_save = 0.0
        self._state_save_interval = 5.0

        # Ignore patterns
        self._ignore_patterns = set(self.config.scan.ignore_patterns)
        self._ignore_patterns.update(DEFAULT_IGNORE_PATTERNS)

    @property
    def state(self) -> ScanState:
        """Get current scan state."""
        return self._state

    @property
    def progress(self) -> ScanProgress:
        """Get current progress."""
        return self._progress

    def scan(
        self,
        drive: Drive,
        mode: ScanMode = ScanMode.QUICK,
        resume_state: dict | None = None,
    ) -> ScanResult:
        """Scan a drive and store results in the database.

        Args:
            drive: Drive to scan
            mode: Type of scan (quick, deep, full)
            resume_state: Optional persisted scan state to resume

        Returns:
            ScanResult with statistics
        """
        if resume_state and resume_state.get("mode"):
            with contextlib.suppress(ValueError):
                mode = ScanMode(resume_state["mode"])

        logger.info(f"Starting {mode.value} scan of {drive.label} ({drive.path})")

        with profile_block(f"scan.{mode.value}"):
            # Reset state
            self._reset_progress()
            self._apply_resume_state(resume_state)
            self._state = ScanState.SCANNING
            if not self._progress.start_time:
                self._progress.start_time = datetime.now()
            self._scan_started_at = self._progress.start_time
            self._progress.state = ScanState.SCANNING
            self._cancel_event.clear()
            self._pause_event.set()

            # Track existing files for this drive
            self._seen_file_ids.clear()
            self._scan_drive_id = drive.id
            self._scan_mode = mode
            self._scan_root = self._normalize_path(drive.path)
            self._resume_path = None
            self._resume_active = False
            self._resume_reached = False

            if resume_state:
                resume_path = resume_state.get("last_path")
                if resume_path:
                    resume_path = self._normalize_path(resume_path)
                    if self._scan_root and resume_path.startswith(self._scan_root):
                        self._resume_path = resume_path
                        self._resume_active = True
                        self._resume_reached = False
                logger.info(f"Resuming scan for {drive.label}")
            else:
                self.db.clear_scan_state(drive.id)
                self._last_state_save = 0.0
            self._persist_scan_state(force=True)

            try:
                # Walk the directory tree
                for file_record in self._walk_directory(drive, mode):
                    # Check for pause
                    self._pause_event.wait()

                    # Check for cancellation
                    if self._cancel_event.is_set():
                        self._state = ScanState.CANCELLED
                        self._progress.state = ScanState.CANCELLED
                        logger.info("Scan cancelled")
                        break

                    # Add to batch
                    self._file_batch.append(file_record)

                    # Flush batch if full
                    if len(self._file_batch) >= self.batch_size:
                        self._flush_batch()

                # Flush remaining files
                if self._file_batch:
                    self._flush_batch()

                # Mark removed files
                if not self._cancel_event.is_set():
                    self._mark_removed_files(drive.id)

                # Update drive stats
                if not self._cancel_event.is_set():
                    self._update_drive_stats(drive)
                    self._state = ScanState.COMPLETED
                    self._progress.state = ScanState.COMPLETED
                    self.db.clear_scan_state(drive.id)
                    logger.info(f"Scan completed: {self._progress.files_found} files found")

            except Exception as e:
                logger.error(f"Scan error: {e}")
                self._state = ScanState.ERROR
                self._progress.state = ScanState.ERROR
                raise
            finally:
                self._scan_drive_id = None
                self._scan_mode = None
                self._scan_root = None
                self._resume_path = None
                self._resume_active = False
                self._resume_reached = False
                self._scan_started_at = None

            # Calculate elapsed time
            if self._progress.start_time:
                self._progress.elapsed_seconds = (
                    datetime.now() - self._progress.start_time
                ).total_seconds()

            # Return result
            result = ScanResult(
                drive_id=drive.id,
                total_files=self._progress.files_found,
                new_files=self._progress.files_new,
                modified_files=self._progress.files_modified,
                removed_files=self._progress.files_removed,
                errors=self._progress.errors,
                duration_seconds=self._progress.elapsed_seconds,
                error_paths=self._progress.error_paths.copy(),
            )

        return result

    def pause(self) -> None:
        """Pause the current scan."""
        if self._state == ScanState.SCANNING:
            self._pause_event.clear()
            self._state = ScanState.PAUSED
            self._progress.state = ScanState.PAUSED
            self._persist_scan_state(force=True)
            logger.info("Scan paused")

    def resume(self) -> None:
        """Resume a paused scan."""
        if self._state == ScanState.PAUSED:
            self._pause_event.set()
            self._state = ScanState.SCANNING
            self._progress.state = ScanState.SCANNING
            logger.info("Scan resumed")

    def cancel(self) -> None:
        """Cancel the current scan."""
        self._cancel_event.set()
        self._pause_event.set()  # Unblock if paused
        if self._scan_drive_id:
            self.db.clear_scan_state(self._scan_drive_id)
        logger.info("Scan cancellation requested")

    def _reset_progress(self) -> None:
        """Reset progress counters."""
        self._progress = ScanProgress()
        self._file_batch.clear()

    def _walk_directory(
        self,
        drive: Drive,
        mode: ScanMode,
    ) -> Generator[FileRecord, None, None]:
        """Walk a directory tree and yield FileRecord objects.

        Args:
            drive: Drive being scanned
            mode: Scan mode

        Yields:
            FileRecord for each file found
        """
        root_path = self._normalize_path(drive.path)
        self._scan_root = root_path

        # Use extended path prefix for long paths on Windows
        if os.name == 'nt' and not root_path.startswith('\\\\?\\'):
            if root_path.startswith('\\\\'):
                # UNC path: \\server\share -> \\?\UNC\server\share
                scan_path = '\\\\?\\UNC\\' + root_path[2:]
            else:
                scan_path = '\\\\?\\' + root_path
        else:
            scan_path = root_path

        try:
            yield from self._scan_directory(scan_path, root_path, drive, mode)
        except PermissionError:
            logger.warning(f"Permission denied for root path: {root_path}")
            self._record_error(root_path, "permission")

    def _scan_directory(
        self,
        scan_path: str,
        display_path: str,
        drive: Drive,
        mode: ScanMode,
    ) -> Generator[FileRecord, None, None]:
        """Recursively scan a directory.

        Args:
            scan_path: Path to scan (may include extended-length prefix)
            display_path: Clean path for display and storage
            drive: Drive being scanned
            mode: Scan mode

        Yields:
            FileRecord for each file found
        """
        try:
            with os.scandir(scan_path) as entries:
                sorted_entries = sorted(entries, key=lambda e: e.name.lower())
                for entry in sorted_entries:
                    # Check for cancellation
                    if self._cancel_event.is_set():
                        return

                    # Check for pause
                    self._pause_event.wait()

                    try:
                        name = entry.name

                        # Skip ignored patterns
                        if self._should_ignore(name):
                            continue

                        # Get clean display path
                        entry_display_path = os.path.join(display_path, name)

                        if self._resume_active and not self._resume_reached and self._should_skip_before_resume(
                            entry_display_path, entry
                        ):
                            continue

                        if entry.is_dir(follow_symlinks=self.config.scan.follow_symlinks):
                            # Skip hidden directories if configured
                            if self.config.scan.ignore_hidden and self._is_hidden(entry):
                                continue

                            self._progress.folders_processed += 1
                            self._progress.current_path = entry_display_path
                            self._update_progress()

                            # Recurse into subdirectory
                            yield from self._scan_directory(
                                entry.path, entry_display_path, drive, mode
                            )

                        elif entry.is_file(follow_symlinks=self.config.scan.follow_symlinks):
                            # Skip hidden files if configured
                            if self.config.scan.ignore_hidden and self._is_hidden(entry):
                                continue

                            self._progress.current_path = entry_display_path
                            # Process file
                            file_record = self._process_file(
                                entry, entry_display_path, drive, mode
                            )
                            if file_record:
                                yield file_record

                    except PermissionError:
                        self._record_error(entry.path, "permission")
                    except OSError as e:
                        if "name is too long" in str(e).lower():
                            self._record_error(entry.path, "path_too_long")
                        else:
                            self._record_error(entry.path, "other")
                            logger.warning(f"Error accessing {entry.path}: {e}")

        except PermissionError:
            self._record_error(scan_path, "permission")
        except OSError as e:
            self._record_error(scan_path, "other")
            logger.warning(f"Error scanning directory {scan_path}: {e}")

    def _process_file(
        self,
        entry: os.DirEntry,
        path: str,
        drive: Drive,
        mode: ScanMode,
    ) -> FileRecord | None:
        """Process a single file entry.

        Args:
            entry: Directory entry from os.scandir
            path: Clean file path
            drive: Drive being scanned
            mode: Scan mode

        Returns:
            FileRecord or None if file should be skipped
        """
        try:
            stat_info = entry.stat(follow_symlinks=False)

            # Skip if too large
            size = stat_info.st_size
            max_size = int(self.config.scan.max_file_size_gb * 1024 * 1024 * 1024)
            if size > max_size:
                logger.debug(f"Skipping large file: {path} ({size} bytes)")
                return None

            # Get timestamps
            try:
                created = datetime.fromtimestamp(stat_info.st_ctime)
            except (OSError, ValueError):
                created = None

            try:
                modified = datetime.fromtimestamp(stat_info.st_mtime)
            except (OSError, ValueError):
                modified = None

            # Get file type info
            filename = os.path.basename(path)
            file_type = os.path.splitext(filename)[1].lower() or None
            mime_type, _ = mimetypes.guess_type(filename)

            # Check if file already exists in database (for quick scan)
            if mode == ScanMode.QUICK:
                existing = self.db.get_file_by_path(drive.id, path)
                if existing:
                    self._seen_file_ids.add(existing.id)

                    # Check if modified
                    if existing.modified == modified and existing.size == size:
                        self.db.update_file_scan_date(existing.id, datetime.now())
                        self._progress.files_unchanged += 1
                        self._progress.files_found += 1
                        self._update_progress()
                        return None  # Skip unchanged file
                    else:
                        self._progress.files_modified += 1
                else:
                    self._progress.files_new += 1
            else:
                # Deep/full scan - check if exists for tracking
                existing = self.db.get_file_by_path(drive.id, path)
                if existing:
                    self._seen_file_ids.add(existing.id)
                    self._progress.files_modified += 1
                else:
                    self._progress.files_new += 1

            self._progress.files_found += 1
            self._update_progress()

            return FileRecord(
                drive_id=drive.id,
                path=path,
                filename=filename,
                size=size,
                created=created,
                modified=modified,
                file_type=file_type,
                mime_type=mime_type,
                scan_date=datetime.now(),
            )

        except (OSError, ValueError) as e:
            self._record_error(path, "other")
            logger.warning(f"Error processing file {path}: {e}")
            return None

    def _should_ignore(self, name: str) -> bool:
        """Check if a file/folder name should be ignored.

        Args:
            name: File or folder name

        Returns:
            True if should be ignored
        """
        # Exact match
        if name in self._ignore_patterns:
            return True

        # Pattern matching
        for pattern in self._ignore_patterns:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern.endswith("*") and name.startswith(pattern[:-1]):
                return True

        return False

    def _should_skip_before_resume(self, entry_path: str, entry: os.DirEntry) -> bool:
        """Skip entries already covered before resume point."""
        if not self._resume_path:
            return False

        resume_path = self._normalize_path(self._resume_path)
        entry_path = self._normalize_path(entry_path)

        if (
            self._path_under(resume_path, entry_path)
            and entry.is_file(follow_symlinks=self.config.scan.follow_symlinks)
            and self._paths_equal(entry_path, resume_path)
        ):
            self._resume_reached = True
            return True
            return False

        comparison = self._compare_paths(entry_path, resume_path)
        if comparison < 0:
            return True
        if comparison > 0:
            self._resume_reached = True
        return False

    def _compare_paths(self, left: str, right: str) -> int:
        """Compare two paths in a stable, platform-aware way."""
        left_norm = os.path.normcase(os.path.normpath(left))
        right_norm = os.path.normcase(os.path.normpath(right))
        if left_norm == right_norm:
            return 0
        return -1 if left_norm < right_norm else 1

    def _paths_equal(self, left: str, right: str) -> bool:
        """Case-insensitive path comparison on Windows."""
        return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))

    def _path_under(self, path: str, root: str) -> bool:
        """Check if path is the same or under root."""
        path_norm = os.path.normcase(os.path.normpath(path))
        root_norm = os.path.normcase(os.path.normpath(root))
        if path_norm == root_norm:
            return True
        return path_norm.startswith(root_norm.rstrip("\\/") + os.sep)

    def _is_hidden(self, entry: os.DirEntry) -> bool:
        """Check if a file/folder is hidden.

        Args:
            entry: Directory entry

        Returns:
            True if hidden
        """
        # Check name starts with dot (Unix hidden)
        if entry.name.startswith('.'):
            return True

        # Check Windows hidden attribute
        if os.name == 'nt':
            try:
                attrs = entry.stat().st_file_attributes
                if attrs & stat.FILE_ATTRIBUTE_HIDDEN:
                    return True
            except (OSError, AttributeError):
                pass

        return False

    def _normalize_path(self, path: str) -> str:
        """Normalize a path for consistent storage.

        Args:
            path: Input path

        Returns:
            Normalized path
        """
        # Convert forward slashes to backslashes on Windows
        if os.name == 'nt':
            path = path.replace('/', '\\')

        # Remove trailing slashes
        path = path.rstrip('\\/')

        return path

    def _apply_resume_state(self, resume_state: dict | None) -> None:
        """Apply persisted scan state to current progress."""
        if not resume_state:
            return
        try:
            self._progress.files_found = int(resume_state.get("files_found", 0))
            self._progress.folders_processed = int(resume_state.get("folders_processed", 0))
            self._progress.files_new = int(resume_state.get("files_new", 0))
            self._progress.files_modified = int(resume_state.get("files_modified", 0))
            self._progress.files_unchanged = int(resume_state.get("files_unchanged", 0))
            self._progress.files_removed = int(resume_state.get("files_removed", 0))
            self._progress.errors = int(resume_state.get("errors", 0))
            self._progress.permission_errors = int(resume_state.get("permission_errors", 0))
            self._progress.path_too_long_errors = int(resume_state.get("path_too_long_errors", 0))
            self._progress.other_errors = int(resume_state.get("other_errors", 0))
            self._progress.current_path = resume_state.get("last_path", "") or ""
            start_time = resume_state.get("start_time")
            if start_time:
                self._progress.start_time = datetime.fromisoformat(start_time)
        except (TypeError, ValueError):
            pass

    def _persist_scan_state(self, force: bool = False) -> None:
        """Persist scan state for resume/recovery."""
        if not self._scan_drive_id or not self._scan_mode:
            return
        if self._state not in (ScanState.SCANNING, ScanState.PAUSED):
            return

        now = time.time()
        if not force and (now - self._last_state_save) < self._state_save_interval:
            return

        self._last_state_save = now
        state = {
            "drive_id": self._scan_drive_id,
            "mode": self._scan_mode.value,
            "state": self._state.value,
            "last_path": self._progress.current_path,
            "files_found": self._progress.files_found,
            "folders_processed": self._progress.folders_processed,
            "files_new": self._progress.files_new,
            "files_modified": self._progress.files_modified,
            "files_unchanged": self._progress.files_unchanged,
            "files_removed": self._progress.files_removed,
            "errors": self._progress.errors,
            "permission_errors": self._progress.permission_errors,
            "path_too_long_errors": self._progress.path_too_long_errors,
            "other_errors": self._progress.other_errors,
            "start_time": self._progress.start_time.isoformat() if self._progress.start_time else None,
            "updated_at": datetime.now().isoformat(),
        }
        self.db.set_scan_state(self._scan_drive_id, state)

    def _flush_batch(self) -> None:
        """Write the current batch of files to the database."""
        if self._file_batch:
            self.db.add_files_batch(self._file_batch)
            logger.debug(f"Flushed {len(self._file_batch)} files to database")
            self._file_batch.clear()

    def _mark_removed_files(self, drive_id: str) -> None:
        """Mark files that no longer exist as deleted.

        Args:
            drive_id: Drive ID to check
        """
        if not drive_id:
            return
        if not self._scan_started_at:
            return
        deleted_count = self.db.mark_files_deleted_before_scan(drive_id, self._scan_started_at)
        if deleted_count:
            logger.info(f"Marked {deleted_count} files as deleted for drive {drive_id}")

    def _update_drive_stats(self, drive: Drive) -> None:
        """Update drive statistics after scan.

        Args:
            drive: Drive to update
        """
        try:
            # Get disk usage
            if os.path.exists(drive.path):
                usage = os.statvfs(drive.path) if os.name != 'nt' else None

                if os.name == 'nt':
                    import ctypes
                    free_bytes = ctypes.c_ulonglong(0)
                    total_bytes = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p(drive.path),
                        None,
                        ctypes.pointer(total_bytes),
                        ctypes.pointer(free_bytes)
                    )
                    total_space = total_bytes.value
                    free_space = free_bytes.value
                else:
                    total_space = usage.f_blocks * usage.f_frsize
                    free_space = usage.f_available * usage.f_frsize

                file_count = self.db.get_file_count(drive.id)

                self.db.update_drive_stats(
                    drive.id,
                    total_space=total_space,
                    free_space=free_space,
                    file_count=file_count
                )
                logger.info(f"Updated drive stats: {file_count} files, "
                           f"{total_space / (1024**3):.1f} GB total, "
                           f"{free_space / (1024**3):.1f} GB free")
        except Exception as e:
            logger.warning(f"Could not update drive stats: {e}")

    def _record_error(self, path: str, error_type: str) -> None:
        """Record an error during scanning.

        Args:
            path: Path where error occurred
            error_type: Type of error (permission, path_too_long, other)
        """
        self._progress.errors += 1

        if error_type == "permission":
            self._progress.permission_errors += 1
        elif error_type == "path_too_long":
            self._progress.path_too_long_errors += 1
        else:
            self._progress.other_errors += 1

        # Keep track of error paths (limit to prevent memory issues)
        if len(self._progress.error_paths) < 1000:
            self._progress.error_paths.append(path)

    def _update_progress(self) -> None:
        """Update progress and call callback if provided."""
        # Calculate speed
        if self._progress.start_time:
            elapsed = (datetime.now() - self._progress.start_time).total_seconds()
            self._progress.elapsed_seconds = elapsed
            if elapsed > 0:
                self._progress.files_per_second = self._progress.files_found / elapsed

        self._persist_scan_state()

        # Call callback
        if self.progress_callback:
            self.progress_callback(self._progress)

    def add_single_file(self, drive: Drive, file_path: str) -> int | None:
        """Add a single file to the database (for incremental/watch scanning).

        Args:
            drive: Drive the file belongs to
            file_path: Absolute path to the file

        Returns:
            File ID if added, None if skipped
        """
        if not os.path.isfile(file_path):
            return None

        try:
            st = os.stat(file_path)
            filename = os.path.basename(file_path)
            file_type = os.path.splitext(filename)[1].lower() or None
            mime_type, _ = mimetypes.guess_type(filename)

            try:
                created = datetime.fromtimestamp(st.st_ctime)
            except (OSError, ValueError):
                created = None
            try:
                modified = datetime.fromtimestamp(st.st_mtime)
            except (OSError, ValueError):
                modified = None

            record = FileRecord(
                drive_id=drive.id,
                path=file_path,
                filename=filename,
                size=st.st_size,
                created=created,
                modified=modified,
                file_type=file_type,
                mime_type=mime_type,
                scan_date=datetime.now(),
            )
            return self.db.add_file(record)
        except (OSError, ValueError) as e:
            logger.warning("Error adding file %s: %s", file_path, e)
            return None

    def detect_corrupt_images(
        self,
        drive_id: str | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> int:
        """Scan image files for corruption and record results in the database.

        Args:
            drive_id: Optional drive to limit scanning
            progress_callback: Called with (processed, total, current_file)

        Returns:
            Number of corrupt files found
        """
        from duplicleaner.utils.jpeg_recovery import JPEGRecovery

        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp',
                     '.tiff', '.tif', '.webp', '.heic', '.heif'}

        with self.db.connection() as conn:
            query = """
                SELECT id, path, file_type, size FROM files
                WHERE is_deleted = FALSE
                  AND file_type IN ({})
            """.format(','.join('?' * len(image_exts)))
            params = list(image_exts)
            if drive_id:
                query += " AND drive_id = ?"
                params.append(drive_id)
            rows = conn.execute(query, params).fetchall()

        total = len(rows)
        corrupt_count = 0
        checker = JPEGRecovery()

        for i, row in enumerate(rows):
            file_id = row["id"]
            path = row["path"]
            file_type = row["file_type"] or ""

            if progress_callback:
                progress_callback(i + 1, total, path)

            if not os.path.exists(path):
                continue

            # Check for corruption
            is_corrupt = False
            corruption_type = "unknown"
            severity = "medium"

            if file_type.lower() in {'.jpg', '.jpeg'}:
                is_corrupt, ctype = checker.is_corrupt_jpeg(path)
                if ctype:
                    corruption_type = ctype
            else:
                # For non-JPEG images, try PIL open+verify
                try:
                    from PIL import Image
                    with Image.open(path) as img:
                        img.verify()
                except Exception as e:
                    is_corrupt = True
                    err = str(e).lower()
                    if "truncated" in err:
                        corruption_type = "truncated"
                    elif "cannot identify" in err:
                        corruption_type = "unreadable"
                    else:
                        corruption_type = "unknown"

            if is_corrupt:
                # Determine severity based on file size
                file_size = row["size"]
                if file_size < 1024:
                    severity = "high"  # Very small, likely empty/header-only
                elif file_size < 10240:
                    severity = "high"  # Suspiciously small for an image
                else:
                    severity = "medium"

                self.db.add_corrupt_file(file_id, corruption_type, severity)
                corrupt_count += 1

        logger.info(f"Corruption scan complete: {corrupt_count} corrupt files found out of {total}")
        return corrupt_count


def is_unc_path(path: str) -> bool:
    """Check if a path is a UNC network path.

    Args:
        path: Path to check

    Returns:
        True if UNC path
    """
    return path.startswith('\\\\') or path.startswith('//')


def get_unc_server_share(path: str) -> tuple[str, str]:
    """Extract server and share from a UNC path.

    Args:
        path: UNC path like \\\\server\\share\\folder

    Returns:
        Tuple of (server, share)
    """
    normalized = path.replace('/', '\\').lstrip('\\')
    parts = normalized.split('\\')

    server = parts[0] if len(parts) > 0 else ""
    share = parts[1] if len(parts) > 1 else ""

    return server, share


@dataclass
class RecoveryResult:
    """Result of a file recovery attempt."""

    file_id: int
    success: bool
    strategy_used: str = ""
    recovered_path: str | None = None
    error: str | None = None
    pixel_recovery_pct: float | None = None


class RecoveryManager:
    """Orchestrates JPEG recovery using multiple strategies in order of aggressiveness."""

    # Recovery strategies in order from least to most aggressive
    STRATEGIES = [
        "pil_tolerant",       # jpeg_recovery.py
        "binary_repair",      # jpeg_binary_repair.py
        "smart_multi_soi",    # jpeg_smart_recovery.py
        "aggressive_offset",  # jpeg_aggressive_recovery.py
        "deep_tolerant",      # jpeg_deep_recovery.py
        "hybrid",             # jpeg_hybrid_recovery.py
    ]

    def __init__(
        self,
        db: Database | None = None,
        recovery_dir: str | None = None,
    ):
        self.db = db or get_database()
        if recovery_dir:
            self._recovery_dir = recovery_dir
        else:
            from duplicleaner.utils.config import get_app_data_dir
            self._recovery_dir = str(get_app_data_dir() / "recovered")
        os.makedirs(self._recovery_dir, exist_ok=True)

    def recover_file(self, file_id: int, file_path: str) -> RecoveryResult:
        """Attempt to recover a corrupt file using progressive strategies.

        Tries each strategy in order, stopping at the first success.

        Args:
            file_id: Database file ID
            file_path: Path to the corrupt file

        Returns:
            RecoveryResult
        """
        if not os.path.exists(file_path):
            return RecoveryResult(file_id=file_id, success=False, error="File not found")

        stem = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(self._recovery_dir, f"{stem}_recovered.jpg")

        # Strategy 1: PIL tolerant mode
        result = self._try_pil_tolerant(file_path, output_path)
        if result:
            self.db.add_recovery_attempt(file_id, "pil_tolerant", True, recovered_path=result)
            return RecoveryResult(file_id=file_id, success=True, strategy_used="pil_tolerant", recovered_path=result)

        # Strategy 2: Binary repair
        result = self._try_binary_repair(file_path, output_path)
        if result:
            self.db.add_recovery_attempt(file_id, "binary_repair", True, recovered_path=result)
            return RecoveryResult(file_id=file_id, success=True, strategy_used="binary_repair", recovered_path=result)

        # Strategy 3: Smart multi-SOI
        result = self._try_smart_recovery(file_path, output_path)
        if result:
            self.db.add_recovery_attempt(file_id, "smart_multi_soi", True, recovered_path=result)
            return RecoveryResult(file_id=file_id, success=True, strategy_used="smart_multi_soi", recovered_path=result)

        # Strategy 4: Aggressive offset scanning
        result = self._try_aggressive_recovery(file_path, output_path)
        if result:
            self.db.add_recovery_attempt(file_id, "aggressive_offset", True, recovered_path=result)
            return RecoveryResult(file_id=file_id, success=True, strategy_used="aggressive_offset", recovered_path=result)

        # Strategy 5: Deep error-tolerant
        result = self._try_deep_recovery(file_path, output_path)
        if result:
            self.db.add_recovery_attempt(file_id, "deep_tolerant", True, recovered_path=result)
            return RecoveryResult(file_id=file_id, success=True, strategy_used="deep_tolerant", recovered_path=result)

        # Strategy 6: Hybrid (combine strategies)
        result = self._try_hybrid_recovery(file_path, output_path)
        if result:
            self.db.add_recovery_attempt(file_id, "hybrid", True, recovered_path=result)
            return RecoveryResult(file_id=file_id, success=True, strategy_used="hybrid", recovered_path=result)

        # All strategies failed
        self.db.add_recovery_attempt(file_id, "all_failed", False)
        return RecoveryResult(file_id=file_id, success=False, error="All recovery strategies failed")

    def _try_pil_tolerant(self, file_path: str, output_path: str) -> str | None:
        """Strategy 1: PIL tolerant mode re-encoding."""
        try:
            from duplicleaner.utils.jpeg_recovery import JPEGRecovery
            recovery = JPEGRecovery(recovery_dir=self._recovery_dir)
            result = recovery.recover_jpeg(file_path, force=True)
            if result.success and result.recovered_path:
                return result.recovered_path
        except Exception as e:
            logger.debug(f"PIL tolerant recovery failed: {e}")
        return None

    def _try_binary_repair(self, file_path: str, output_path: str) -> str | None:
        """Strategy 2: Binary-level JPEG marker reconstruction."""
        try:
            from duplicleaner.utils.jpeg_binary_repair import JPEGBinaryRepair
            repair = JPEGBinaryRepair()
            result_path = repair.repair(file_path, output_path)
            if result_path and os.path.exists(result_path):
                # Verify result is a valid image
                from PIL import Image
                with Image.open(result_path) as img:
                    img.verify()
                return result_path
        except Exception as e:
            logger.debug(f"Binary repair failed: {e}")
        return None

    def _try_smart_recovery(self, file_path: str, output_path: str) -> str | None:
        """Strategy 3: Multi-SOI marker extraction."""
        try:
            from duplicleaner.utils.jpeg_smart_recovery import JPEGSmartRecovery
            recovery = JPEGSmartRecovery()
            results = recovery.extract_images(file_path, self._recovery_dir)
            if results:
                # Return the largest successfully extracted image
                best = max(results, key=lambda p: os.path.getsize(p) if os.path.exists(p) else 0)
                return best
        except Exception as e:
            logger.debug(f"Smart recovery failed: {e}")
        return None

    def _try_aggressive_recovery(self, file_path: str, output_path: str) -> str | None:
        """Strategy 4: EXIF dimensions + offset scanning."""
        try:
            from duplicleaner.utils.jpeg_aggressive_recovery import JPEGAggressiveRecovery
            recovery = JPEGAggressiveRecovery()
            result_path = recovery.recover(file_path, output_path)
            if result_path and os.path.exists(result_path):
                from PIL import Image
                with Image.open(result_path) as img:
                    img.verify()
                return result_path
        except Exception as e:
            logger.debug(f"Aggressive recovery failed: {e}")
        return None

    def _try_deep_recovery(self, file_path: str, output_path: str) -> str | None:
        """Strategy 5: Error-tolerant decoding with EOI padding."""
        try:
            from duplicleaner.utils.jpeg_deep_recovery import JPEGDeepRecovery
            recovery = JPEGDeepRecovery()
            result_path = recovery.recover(file_path, output_path)
            if result_path and os.path.exists(result_path):
                from PIL import Image
                with Image.open(result_path) as img:
                    img.verify()
                return result_path
        except Exception as e:
            logger.debug(f"Deep recovery failed: {e}")
        return None

    def _try_hybrid_recovery(self, file_path: str, output_path: str) -> str | None:
        """Strategy 6: Combine multiple strategies."""
        try:
            from duplicleaner.utils.jpeg_hybrid_recovery import JPEGHybridRecovery
            recovery = JPEGHybridRecovery()
            result_path = recovery.recover_hybrid(file_path, output_path)
            if result_path and os.path.exists(result_path):
                return result_path
        except Exception as e:
            logger.debug(f"Hybrid recovery failed: {e}")
        return None

    def recover_batch(
        self,
        corrupt_files: list[dict],
        progress_callback: Callable[[int, int, str, bool], None] | None = None,
    ) -> tuple[int, int]:
        """Recover a batch of corrupt files.

        Args:
            corrupt_files: List of dicts from db.get_corrupt_files()
            progress_callback: Called with (processed, total, filename, success)

        Returns:
            Tuple of (success_count, fail_count)
        """
        total = len(corrupt_files)
        success_count = 0
        fail_count = 0

        for i, cf in enumerate(corrupt_files):
            file_id = cf["file_id"]
            path = cf["path"]
            filename = cf.get("filename", os.path.basename(path))

            result = self.recover_file(file_id, path)

            if result.success:
                success_count += 1
                # Mark as no longer corrupt
                self.db.remove_corrupt_file(file_id)
            else:
                fail_count += 1

            if progress_callback:
                progress_callback(i + 1, total, filename, result.success)

        logger.info(f"Batch recovery: {success_count} recovered, {fail_count} failed out of {total}")
        return success_count, fail_count
