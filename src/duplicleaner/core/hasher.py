"""File Hasher for DupliCleaner.

Computes file hashes for duplicate detection using a two-phase approach:
1. Quick hash (xxHash) of first+last 64KB for fast elimination
2. Full hash (SHA-256) for verification of potential duplicates
"""

import hashlib
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Generator, Optional

import xxhash

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import FileRecord
from duplicleaner.utils.config import get_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


# Default chunk sizes
QUICK_HASH_CHUNK_SIZE = 64 * 1024  # 64 KB for quick hash
FULL_HASH_CHUNK_SIZE = 1024 * 1024  # 1 MB for full hash


class HashState(Enum):
    """Current state of the hasher."""

    IDLE = "idle"
    HASHING = "hashing"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class HashProgress:
    """Progress information for hashing operation."""

    files_to_hash: int = 0
    files_completed: int = 0
    files_skipped: int = 0
    bytes_processed: int = 0
    bytes_total: int = 0
    current_file: str = ""
    current_file_progress: float = 0.0  # 0.0 to 1.0 for large files
    start_time: Optional[datetime] = None
    elapsed_seconds: float = 0.0
    files_per_second: float = 0.0
    bytes_per_second: float = 0.0
    state: HashState = HashState.IDLE
    errors: int = 0
    error_paths: list[str] = field(default_factory=list)


@dataclass
class HashResult:
    """Result of a hashing operation."""

    files_hashed: int
    files_skipped: int
    duplicate_candidates: int  # Files with matching quick hashes
    exact_duplicates: int  # Files with matching full hashes
    errors: int
    duration_seconds: float


class Hasher:
    """File hasher with progress tracking and pause/resume support."""

    def __init__(
        self,
        db: Optional[Database] = None,
        quick_hash_size: int = QUICK_HASH_CHUNK_SIZE,
        chunk_size: int = FULL_HASH_CHUNK_SIZE,
        progress_callback: Optional[Callable[[HashProgress], None]] = None,
    ):
        """Initialize the hasher.

        Args:
            db: Database instance (uses singleton if not provided)
            quick_hash_size: Bytes to read for quick hash (first + last)
            chunk_size: Chunk size for streaming full hash
            progress_callback: Function called with progress updates
        """
        self.db = db or get_database()
        self.config = get_config()
        self.quick_hash_size = quick_hash_size
        self.chunk_size = chunk_size
        self.progress_callback = progress_callback

        self._state = HashState.IDLE
        self._progress = HashProgress()
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._cancel_event = threading.Event()

    @property
    def state(self) -> HashState:
        """Get current hash state."""
        return self._state

    @property
    def progress(self) -> HashProgress:
        """Get current progress."""
        return self._progress

    def compute_quick_hash(self, file_path: str) -> Optional[str]:
        """Compute quick hash (xxHash) of file's first and last chunks.

        Args:
            file_path: Path to file

        Returns:
            Hex string of hash, or None on error
        """
        try:
            file_size = os.path.getsize(file_path)

            hasher = xxhash.xxh64()

            with open(file_path, "rb") as f:
                # Read first chunk
                first_chunk = f.read(self.quick_hash_size)
                hasher.update(first_chunk)

                # If file is large enough, read last chunk
                if file_size > self.quick_hash_size * 2:
                    f.seek(-self.quick_hash_size, os.SEEK_END)
                    last_chunk = f.read(self.quick_hash_size)
                    hasher.update(last_chunk)
                elif file_size > self.quick_hash_size:
                    # File is between 1x and 2x chunk size, read remainder
                    remaining = f.read()
                    hasher.update(remaining)

                # Include file size in hash to differentiate same-content different-size files
                hasher.update(str(file_size).encode())

            return hasher.hexdigest()

        except (OSError, IOError) as e:
            logger.warning(f"Error computing quick hash for {file_path}: {e}")
            return None

    def compute_full_hash(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[str]:
        """Compute full SHA-256 hash of file.

        Args:
            file_path: Path to file
            progress_callback: Optional callback with progress (0.0 to 1.0)

        Returns:
            Hex string of hash, or None on error
        """
        try:
            file_size = os.path.getsize(file_path)
            bytes_read = 0

            hasher = hashlib.sha256()

            with open(file_path, "rb") as f:
                while True:
                    # Check for pause/cancel
                    self._pause_event.wait()
                    if self._cancel_event.is_set():
                        return None

                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break

                    hasher.update(chunk)
                    bytes_read += len(chunk)

                    # Update progress
                    if progress_callback and file_size > 0:
                        progress_callback(bytes_read / file_size)

            return hasher.hexdigest()

        except (OSError, IOError) as e:
            logger.warning(f"Error computing full hash for {file_path}: {e}")
            return None

    def hash_files(
        self,
        drive_id: Optional[str] = None,
        force_rehash: bool = False,
    ) -> HashResult:
        """Hash files that need hashing (potential duplicates by size).

        Args:
            drive_id: Optional drive ID to limit hashing
            force_rehash: If True, rehash all files regardless of cache

        Returns:
            HashResult with statistics
        """
        logger.info(f"Starting hash operation (drive={drive_id}, force={force_rehash})")

        # Reset state
        self._reset_progress()
        self._state = HashState.HASHING
        self._progress.state = HashState.HASHING
        self._progress.start_time = datetime.now()
        self._cancel_event.clear()
        self._pause_event.set()

        files_hashed = 0
        files_skipped = 0
        duplicate_candidates = 0
        exact_duplicates = 0
        errors = 0

        try:
            # Get files that need hashing (files sharing size with others)
            files_to_hash = self.db.get_files_needing_hash(drive_id)
            self._progress.files_to_hash = len(files_to_hash)

            # Calculate total bytes
            self._progress.bytes_total = sum(f.size for f in files_to_hash)

            logger.info(f"Found {len(files_to_hash)} files to hash "
                       f"({self._progress.bytes_total / (1024**3):.2f} GB)")

            # Phase 1: Compute quick hashes
            quick_hash_groups: dict[str, list[FileRecord]] = {}

            for file in files_to_hash:
                # Check for pause/cancel
                self._pause_event.wait()
                if self._cancel_event.is_set():
                    self._state = HashState.CANCELLED
                    self._progress.state = HashState.CANCELLED
                    break

                self._progress.current_file = file.path
                self._update_progress()

                # Skip if already has quick hash and not forcing rehash
                if file.quick_hash and not force_rehash:
                    quick_hash = file.quick_hash
                else:
                    quick_hash = self.compute_quick_hash(file.path)
                    if quick_hash:
                        self.db.update_file_hash(file.id, quick_hash=quick_hash)
                    else:
                        errors += 1
                        self._progress.errors += 1
                        self._progress.error_paths.append(file.path)
                        continue

                # Group by quick hash
                if quick_hash not in quick_hash_groups:
                    quick_hash_groups[quick_hash] = []
                quick_hash_groups[quick_hash].append(file)

                self._progress.files_completed += 1
                self._progress.bytes_processed += file.size
                self._update_progress()

            # Filter to only groups with potential duplicates
            potential_duplicates = {
                h: files for h, files in quick_hash_groups.items()
                if len(files) > 1
            }
            duplicate_candidates = sum(len(files) for files in potential_duplicates.values())

            logger.info(f"Found {len(potential_duplicates)} groups with "
                       f"{duplicate_candidates} potential duplicates")

            # Phase 2: Compute full hashes for potential duplicates
            for quick_hash, files in potential_duplicates.items():
                if self._cancel_event.is_set():
                    break

                for file in files:
                    # Check for pause/cancel
                    self._pause_event.wait()
                    if self._cancel_event.is_set():
                        break

                    self._progress.current_file = file.path
                    self._progress.current_file_progress = 0.0
                    self._update_progress()

                    # Skip if already has full hash and not forcing rehash
                    if file.content_hash and not force_rehash:
                        files_skipped += 1
                        self._progress.files_skipped += 1
                        continue

                    # Compute full hash with progress for large files
                    def file_progress(p: float) -> None:
                        self._progress.current_file_progress = p
                        self._update_progress()

                    content_hash = self.compute_full_hash(
                        file.path,
                        progress_callback=file_progress if file.size > 100 * 1024 * 1024 else None
                    )

                    if content_hash:
                        self.db.update_file_hash(file.id, content_hash=content_hash)
                        files_hashed += 1

                        # Check for exact duplicates
                        matching_files = self.db.get_files_by_hash(content_hash)
                        if len(matching_files) > 1:
                            exact_duplicates += 1
                    else:
                        if not self._cancel_event.is_set():
                            errors += 1
                            self._progress.errors += 1
                            self._progress.error_paths.append(file.path)

            if not self._cancel_event.is_set():
                self._state = HashState.COMPLETED
                self._progress.state = HashState.COMPLETED
                logger.info(f"Hashing completed: {files_hashed} files hashed, "
                           f"{exact_duplicates} exact duplicates found")

        except Exception as e:
            logger.error(f"Hash error: {e}")
            self._state = HashState.ERROR
            self._progress.state = HashState.ERROR
            raise

        # Calculate elapsed time
        if self._progress.start_time:
            self._progress.elapsed_seconds = (
                datetime.now() - self._progress.start_time
            ).total_seconds()

        return HashResult(
            files_hashed=files_hashed,
            files_skipped=files_skipped,
            duplicate_candidates=duplicate_candidates,
            exact_duplicates=exact_duplicates,
            errors=errors,
            duration_seconds=self._progress.elapsed_seconds,
        )

    def hash_single_file(
        self,
        file_path: str,
        compute_full: bool = True,
    ) -> tuple[Optional[str], Optional[str]]:
        """Hash a single file.

        Args:
            file_path: Path to file
            compute_full: Whether to compute full hash (default True)

        Returns:
            Tuple of (quick_hash, full_hash)
        """
        quick_hash = self.compute_quick_hash(file_path)

        full_hash = None
        if compute_full:
            full_hash = self.compute_full_hash(file_path)

        return quick_hash, full_hash

    def pause(self) -> None:
        """Pause the current hashing operation."""
        if self._state == HashState.HASHING:
            self._pause_event.clear()
            self._state = HashState.PAUSED
            self._progress.state = HashState.PAUSED
            logger.info("Hashing paused")

    def resume(self) -> None:
        """Resume a paused hashing operation."""
        if self._state == HashState.PAUSED:
            self._pause_event.set()
            self._state = HashState.HASHING
            self._progress.state = HashState.HASHING
            logger.info("Hashing resumed")

    def cancel(self) -> None:
        """Cancel the current hashing operation."""
        self._cancel_event.set()
        self._pause_event.set()  # Unblock if paused
        logger.info("Hashing cancellation requested")

    def _reset_progress(self) -> None:
        """Reset progress counters."""
        self._progress = HashProgress()

    def _update_progress(self) -> None:
        """Update progress and call callback if provided."""
        # Calculate speed
        if self._progress.start_time:
            elapsed = (datetime.now() - self._progress.start_time).total_seconds()
            self._progress.elapsed_seconds = elapsed
            if elapsed > 0:
                self._progress.files_per_second = self._progress.files_completed / elapsed
                self._progress.bytes_per_second = self._progress.bytes_processed / elapsed

        # Call callback
        if self.progress_callback:
            self.progress_callback(self._progress)


def compute_file_hash(file_path: str, algorithm: str = "sha256") -> Optional[str]:
    """Convenience function to compute a file hash.

    Args:
        file_path: Path to file
        algorithm: Hash algorithm (sha256, md5, xxhash)

    Returns:
        Hex string of hash, or None on error
    """
    try:
        if algorithm == "xxhash":
            hasher = xxhash.xxh64()
        else:
            hasher = hashlib.new(algorithm)

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(FULL_HASH_CHUNK_SIZE), b""):
                hasher.update(chunk)

        return hasher.hexdigest()

    except (OSError, IOError, ValueError) as e:
        logger.warning(f"Error computing {algorithm} hash for {file_path}: {e}")
        return None


def verify_file_hash(file_path: str, expected_hash: str, algorithm: str = "sha256") -> bool:
    """Verify a file matches an expected hash.

    Args:
        file_path: Path to file
        expected_hash: Expected hash value
        algorithm: Hash algorithm used

    Returns:
        True if hash matches
    """
    actual_hash = compute_file_hash(file_path, algorithm)
    return actual_hash is not None and actual_hash.lower() == expected_hash.lower()
