"""Action engine for file operations.

Handles quarantine, trash, delete, copy, move, and link operations
with full audit logging and undo support.
"""

import contextlib
import hashlib
import json
import os
import shutil
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import Event

from ..db.database import Database
from ..db.models import ActionLogEntry, ActionType
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ActionStatus(Enum):
    """Status of an action execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNDONE = "undone"


@dataclass
class PendingAction:
    """Represents an action to be executed."""

    action_type: ActionType
    source_path: str
    dest_path: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    metadata: dict | None = None


@dataclass
class ActionResult:
    """Result of executing an action."""

    action: PendingAction
    status: ActionStatus
    error_message: str | None = None
    log_entry_id: int | None = None
    elapsed_seconds: float = 0.0


@dataclass
class OperationProgress:
    """Tracks progress of a batch operation."""

    total_files: int = 0
    completed_files: int = 0
    total_bytes: int = 0
    completed_bytes: int = 0
    current_file: str = ""
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    phase: str = "preparing"
    started_at: datetime | None = None
    is_cancelled: bool = False
    is_paused: bool = False

    @property
    def percent_complete(self) -> float:
        """Calculate completion percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.completed_files / self.total_files) * 100

    @property
    def elapsed_seconds(self) -> float:
        """Calculate elapsed time."""
        if self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return 0.0

    @property
    def files_per_second(self) -> float:
        """Calculate processing rate."""
        elapsed = self.elapsed_seconds
        if elapsed > 0:
            return self.completed_files / elapsed
        return 0.0


class ActionEngine:
    """Engine for executing file operations with audit logging."""

    # System folders that should never be deleted from
    PROTECTED_PATHS = {
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
        "C:\\ProgramData",
        "C:\\Users\\Default",
        "C:\\$Recycle.Bin",
    }

    def __init__(
        self,
        db: Database,
        quarantine_folder: str | None = None,
        verify_copies: bool = True,
        dry_run: bool = False,
    ):
        """Initialize action engine.

        Args:
            db: Database instance for logging
            quarantine_folder: Folder for quarantined files
            verify_copies: Whether to verify copies with hash check
            dry_run: If True, simulate operations without executing
        """
        self.db = db
        self.quarantine_folder = quarantine_folder or os.path.join(
            os.path.expanduser("~"), "DupliCleaner_Quarantine"
        )
        self.verify_copies = verify_copies
        self.dry_run = dry_run

        # Pending actions queue
        self.pending_actions: list[PendingAction] = []

        # Progress tracking
        self.progress = OperationProgress()
        self._cancel_event = Event()
        self._pause_event = Event()
        self._pause_event.set()  # Not paused by default

        # Callbacks
        self._progress_callback: Callable[[OperationProgress], None] | None = None

    def set_progress_callback(
        self, callback: Callable[[OperationProgress], None] | None
    ) -> None:
        """Set callback for progress updates."""
        self._progress_callback = callback

    def _notify_progress(self) -> None:
        """Notify callback of progress update."""
        if self._progress_callback:
            try:
                self._progress_callback(self.progress)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    def _is_protected_path(self, path: str) -> bool:
        """Check if path is in a protected system folder."""
        path_lower = path.lower()
        return any(path_lower.startswith(protected.lower()) for protected in self.PROTECTED_PATHS)

    def _compute_file_hash(self, path: str) -> str | None:
        """Compute SHA-256 hash of a file."""
        try:
            sha256 = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash {path}: {e}")
            return None

    def _get_quarantine_path(self, source_path: str) -> str:
        """Generate quarantine path preserving folder structure."""
        # Create date folder
        date_folder = datetime.now().strftime("%Y-%m-%d")

        # Convert source path to safe folder name
        # \\NAS\Photos\file.jpg -> NAS_Photos
        source_dir = os.path.dirname(source_path)
        if source_dir.startswith("\\\\"):
            # UNC path
            safe_dir = source_dir[2:].replace("\\", "_").replace("/", "_")
        else:
            # Local path - use drive letter + path
            drive, rest = os.path.splitdrive(source_dir)
            safe_dir = drive.rstrip(":") + rest.replace("\\", "_").replace("/", "_")

        # Clean up multiple underscores
        while "__" in safe_dir:
            safe_dir = safe_dir.replace("__", "_")
        safe_dir = safe_dir.strip("_")

        filename = os.path.basename(source_path)
        return os.path.join(self.quarantine_folder, date_folder, safe_dir, filename)

    def _ensure_directory(self, path: str) -> bool:
        """Ensure directory exists, create if needed."""
        try:
            os.makedirs(path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            return False

    def _make_writable(self, path: str) -> None:
        """Make a file writable if it's read-only."""
        try:
            if os.path.exists(path):
                current_mode = os.stat(path).st_mode
                if not (current_mode & stat.S_IWRITE):
                    os.chmod(path, current_mode | stat.S_IWRITE)
        except Exception as e:
            logger.warning(f"Could not make {path} writable: {e}")

    def _log_action(
        self,
        action_type: ActionType,
        source_path: str,
        dest_path: str | None = None,
        file_hash: str | None = None,
        file_size: int | None = None,
        reversible: bool = True,
        metadata: dict | None = None,
    ) -> int | None:
        """Log an action to the database."""
        try:
            entry = ActionLogEntry(
                action_type=action_type,
                source_path=source_path,
                dest_path=dest_path,
                file_hash=file_hash,
                file_size=file_size,
                reversible=reversible,
                metadata=json.dumps(metadata) if metadata else None,
            )
            return self.db.log_action(entry)
        except Exception as e:
            logger.error(f"Failed to log action: {e}")
            return None

    # === Individual Operations ===

    def quarantine(
        self,
        source_path: str,
        file_hash: str | None = None,
    ) -> ActionResult:
        """Move a file to quarantine folder.

        Args:
            source_path: Path to file to quarantine
            file_hash: Pre-computed hash (will compute if not provided)

        Returns:
            ActionResult with status
        """
        action = PendingAction(
            action_type=ActionType.QUARANTINE,
            source_path=source_path,
            file_hash=file_hash,
        )
        start_time = time.time()

        # Validate
        if not os.path.exists(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="File not found",
                elapsed_seconds=time.time() - start_time,
            )

        if self._is_protected_path(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Cannot quarantine files from protected system folders",
                elapsed_seconds=time.time() - start_time,
            )

        # Get file info
        try:
            file_size = os.path.getsize(source_path)
            if not file_hash:
                file_hash = self._compute_file_hash(source_path)
        except Exception as e:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to read file: {e}",
                elapsed_seconds=time.time() - start_time,
            )

        # Generate quarantine path
        dest_path = self._get_quarantine_path(source_path)
        action.dest_path = dest_path
        action.file_size = file_size
        action.file_hash = file_hash

        if self.dry_run:
            logger.info(f"[DRY RUN] Would quarantine: {source_path} -> {dest_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        # Create destination directory
        dest_dir = os.path.dirname(dest_path)
        if not self._ensure_directory(dest_dir):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to create quarantine directory: {dest_dir}",
                elapsed_seconds=time.time() - start_time,
            )

        # Handle destination conflicts
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(dest_path)
            counter = 1
            while os.path.exists(dest_path):
                dest_path = f"{base}_{counter}{ext}"
                counter += 1
            action.dest_path = dest_path

        # Move file
        try:
            self._make_writable(source_path)
            shutil.move(source_path, dest_path)

            # Log action
            log_id = self._log_action(
                ActionType.QUARANTINE,
                source_path,
                dest_path,
                file_hash,
                file_size,
                reversible=True,
            )

            logger.info(f"Quarantined: {source_path} -> {dest_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                log_entry_id=log_id,
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to quarantine {source_path}: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def send_to_trash(self, source_path: str) -> ActionResult:
        """Send a file to system trash/recycle bin.

        Args:
            source_path: Path to file to trash

        Returns:
            ActionResult with status
        """
        action = PendingAction(
            action_type=ActionType.TRASH,
            source_path=source_path,
        )
        start_time = time.time()

        # Validate
        if not os.path.exists(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="File not found",
                elapsed_seconds=time.time() - start_time,
            )

        if self._is_protected_path(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Cannot trash files from protected system folders",
                elapsed_seconds=time.time() - start_time,
            )

        # Get file info
        try:
            file_size = os.path.getsize(source_path)
            file_hash = self._compute_file_hash(source_path)
            action.file_size = file_size
            action.file_hash = file_hash
        except Exception as e:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to read file: {e}",
                elapsed_seconds=time.time() - start_time,
            )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would trash: {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        # Try to use send2trash if available
        try:
            import send2trash

            send2trash.send2trash(source_path)

            # Log action
            log_id = self._log_action(
                ActionType.TRASH,
                source_path,
                None,
                file_hash,
                file_size,
                reversible=True,  # Can restore from recycle bin
            )

            logger.info(f"Sent to trash: {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                log_entry_id=log_id,
                elapsed_seconds=time.time() - start_time,
            )

        except ImportError:
            # Fallback: move to quarantine
            logger.warning("send2trash not available, using quarantine instead")
            return self.quarantine(source_path, file_hash)

        except Exception as e:
            logger.error(f"Failed to trash {source_path}: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def delete_permanently(
        self,
        source_path: str,
        confirm: bool = False,
    ) -> ActionResult:
        """Permanently delete a file.

        Args:
            source_path: Path to file to delete
            confirm: Must be True to actually delete

        Returns:
            ActionResult with status
        """
        action = PendingAction(
            action_type=ActionType.DELETE,
            source_path=source_path,
        )
        start_time = time.time()

        if not confirm:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Permanent delete requires confirm=True",
                elapsed_seconds=time.time() - start_time,
            )

        # Validate
        if not os.path.exists(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="File not found",
                elapsed_seconds=time.time() - start_time,
            )

        if self._is_protected_path(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Cannot delete files from protected system folders",
                elapsed_seconds=time.time() - start_time,
            )

        # Get file info for logging
        try:
            file_size = os.path.getsize(source_path)
            file_hash = self._compute_file_hash(source_path)
            action.file_size = file_size
            action.file_hash = file_hash
        except Exception as e:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to read file: {e}",
                elapsed_seconds=time.time() - start_time,
            )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete: {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        # Delete file
        try:
            self._make_writable(source_path)
            os.remove(source_path)

            # Log action (not reversible)
            log_id = self._log_action(
                ActionType.DELETE,
                source_path,
                None,
                file_hash,
                file_size,
                reversible=False,
            )

            logger.info(f"Permanently deleted: {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                log_entry_id=log_id,
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to delete {source_path}: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def copy_file(
        self,
        source_path: str,
        dest_path: str,
        overwrite: bool = False,
    ) -> ActionResult:
        """Copy a file to a new location.

        Args:
            source_path: Path to source file
            dest_path: Path to destination
            overwrite: Whether to overwrite existing file

        Returns:
            ActionResult with status
        """
        action = PendingAction(
            action_type=ActionType.COPY,
            source_path=source_path,
            dest_path=dest_path,
        )
        start_time = time.time()

        # Validate source
        if not os.path.exists(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Source file not found",
                elapsed_seconds=time.time() - start_time,
            )

        # Check destination
        if os.path.exists(dest_path) and not overwrite:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Destination file exists (use overwrite=True)",
                elapsed_seconds=time.time() - start_time,
            )

        # Get file info
        try:
            file_size = os.path.getsize(source_path)
            file_hash = self._compute_file_hash(source_path) if self.verify_copies else None
            action.file_size = file_size
            action.file_hash = file_hash
        except Exception as e:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to read source: {e}",
                elapsed_seconds=time.time() - start_time,
            )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would copy: {source_path} -> {dest_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        # Create destination directory
        dest_dir = os.path.dirname(dest_path)
        if dest_dir and not self._ensure_directory(dest_dir):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to create directory: {dest_dir}",
                elapsed_seconds=time.time() - start_time,
            )

        # Copy file
        try:
            shutil.copy2(source_path, dest_path)

            # Verify copy if enabled
            if self.verify_copies and file_hash:
                dest_hash = self._compute_file_hash(dest_path)
                if dest_hash != file_hash:
                    # Remove failed copy
                    os.remove(dest_path)
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Copy verification failed - hash mismatch",
                        elapsed_seconds=time.time() - start_time,
                    )

            # Log action
            log_id = self._log_action(
                ActionType.COPY,
                source_path,
                dest_path,
                file_hash,
                file_size,
                reversible=True,  # Can undo by deleting copy
            )

            logger.info(f"Copied: {source_path} -> {dest_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                log_entry_id=log_id,
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to copy {source_path}: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def move_file(
        self,
        source_path: str,
        dest_path: str,
        overwrite: bool = False,
    ) -> ActionResult:
        """Move a file to a new location.

        Args:
            source_path: Path to source file
            dest_path: Path to destination
            overwrite: Whether to overwrite existing file

        Returns:
            ActionResult with status
        """
        action = PendingAction(
            action_type=ActionType.MOVE,
            source_path=source_path,
            dest_path=dest_path,
        )
        start_time = time.time()

        # Validate source
        if not os.path.exists(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Source file not found",
                elapsed_seconds=time.time() - start_time,
            )

        if self._is_protected_path(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Cannot move files from protected system folders",
                elapsed_seconds=time.time() - start_time,
            )

        # Check destination
        if os.path.exists(dest_path) and not overwrite:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Destination file exists (use overwrite=True)",
                elapsed_seconds=time.time() - start_time,
            )

        # Get file info
        try:
            file_size = os.path.getsize(source_path)
            file_hash = self._compute_file_hash(source_path)
            action.file_size = file_size
            action.file_hash = file_hash
        except Exception as e:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to read source: {e}",
                elapsed_seconds=time.time() - start_time,
            )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would move: {source_path} -> {dest_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        # Create destination directory
        dest_dir = os.path.dirname(dest_path)
        if dest_dir and not self._ensure_directory(dest_dir):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to create directory: {dest_dir}",
                elapsed_seconds=time.time() - start_time,
            )

        # Move file
        try:
            self._make_writable(source_path)
            if os.path.exists(dest_path) and overwrite:
                os.remove(dest_path)
            shutil.move(source_path, dest_path)

            # Log action
            log_id = self._log_action(
                ActionType.MOVE,
                source_path,
                dest_path,
                file_hash,
                file_size,
                reversible=True,  # Can undo by moving back
            )

            logger.info(f"Moved: {source_path} -> {dest_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                log_entry_id=log_id,
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to move {source_path}: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def create_hard_link(
        self,
        source_path: str,
        link_path: str,
    ) -> ActionResult:
        """Create a hard link to a file.

        Args:
            source_path: Path to existing file
            link_path: Path for the hard link

        Returns:
            ActionResult with status
        """
        action = PendingAction(
            action_type=ActionType.LINK,
            source_path=source_path,
            dest_path=link_path,
            metadata={"link_type": "hard"},
        )
        start_time = time.time()

        # Validate source
        if not os.path.exists(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Source file not found",
                elapsed_seconds=time.time() - start_time,
            )

        # Check if same volume (required for hard links)
        source_drive = os.path.splitdrive(source_path)[0].upper()
        link_drive = os.path.splitdrive(link_path)[0].upper()
        if source_drive != link_drive:
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Hard links require same volume",
                elapsed_seconds=time.time() - start_time,
            )

        # Check destination
        if os.path.exists(link_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Link path already exists",
                elapsed_seconds=time.time() - start_time,
            )

        action.file_size = os.path.getsize(source_path)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create hard link: {link_path} -> {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        # Create destination directory
        link_dir = os.path.dirname(link_path)
        if link_dir and not self._ensure_directory(link_dir):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to create directory: {link_dir}",
                elapsed_seconds=time.time() - start_time,
            )

        # Create hard link
        try:
            os.link(source_path, link_path)

            # Log action
            log_id = self._log_action(
                ActionType.LINK,
                source_path,
                link_path,
                None,
                action.file_size,
                reversible=True,
                metadata={"link_type": "hard"},
            )

            logger.info(f"Created hard link: {link_path} -> {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                log_entry_id=log_id,
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to create hard link: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def create_symbolic_link(
        self,
        source_path: str,
        link_path: str,
    ) -> ActionResult:
        """Create a symbolic link to a file.

        Args:
            source_path: Path to existing file
            link_path: Path for the symbolic link

        Returns:
            ActionResult with status
        """
        action = PendingAction(
            action_type=ActionType.LINK,
            source_path=source_path,
            dest_path=link_path,
            metadata={"link_type": "symbolic"},
        )
        start_time = time.time()

        # Validate source
        if not os.path.exists(source_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Source file not found",
                elapsed_seconds=time.time() - start_time,
            )

        # Check destination
        if os.path.exists(link_path):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message="Link path already exists",
                elapsed_seconds=time.time() - start_time,
            )

        action.file_size = os.path.getsize(source_path)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create symlink: {link_path} -> {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        # Create destination directory
        link_dir = os.path.dirname(link_path)
        if link_dir and not self._ensure_directory(link_dir):
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=f"Failed to create directory: {link_dir}",
                elapsed_seconds=time.time() - start_time,
            )

        # Create symbolic link
        try:
            os.symlink(source_path, link_path)

            # Log action
            log_id = self._log_action(
                ActionType.LINK,
                source_path,
                link_path,
                None,
                action.file_size,
                reversible=True,
                metadata={"link_type": "symbolic"},
            )

            logger.info(f"Created symlink: {link_path} -> {source_path}")
            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                log_entry_id=log_id,
                elapsed_seconds=time.time() - start_time,
            )

        except OSError as e:
            if e.winerror == 1314:  # Privilege not held
                return ActionResult(
                    action=action,
                    status=ActionStatus.FAILED,
                    error_message="Creating symlinks requires administrator privileges on Windows",
                    elapsed_seconds=time.time() - start_time,
                )
            raise

        except Exception as e:
            logger.error(f"Failed to create symlink: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    # === Batch Operations ===

    def add_pending(self, action: PendingAction) -> None:
        """Add an action to the pending queue."""
        self.pending_actions.append(action)

    def add_pending_batch(self, actions: list[PendingAction]) -> None:
        """Add multiple actions to the pending queue."""
        self.pending_actions.extend(actions)

    def clear_pending(self) -> None:
        """Clear all pending actions."""
        self.pending_actions.clear()

    def get_pending_summary(self) -> dict:
        """Get summary of pending actions."""
        summary = {
            ActionType.QUARANTINE: {"count": 0, "size": 0},
            ActionType.TRASH: {"count": 0, "size": 0},
            ActionType.DELETE: {"count": 0, "size": 0},
            ActionType.COPY: {"count": 0, "size": 0},
            ActionType.MOVE: {"count": 0, "size": 0},
            ActionType.LINK: {"count": 0, "size": 0},
        }

        for action in self.pending_actions:
            if action.action_type in summary:
                summary[action.action_type]["count"] += 1
                if action.file_size:
                    summary[action.action_type]["size"] += action.file_size

        return summary

    def execute_pending(
        self,
        confirm_delete: bool = False,
    ) -> list[ActionResult]:
        """Execute all pending actions.

        Args:
            confirm_delete: Must be True if any pending actions are DELETE

        Returns:
            List of ActionResults
        """
        results = []

        # Check for deletes
        has_deletes = any(a.action_type == ActionType.DELETE for a in self.pending_actions)
        if has_deletes and not confirm_delete:
            logger.error("Pending actions include DELETEs but confirm_delete=False")
            return []

        # Reset progress
        self.progress = OperationProgress(
            total_files=len(self.pending_actions),
            total_bytes=sum(a.file_size or 0 for a in self.pending_actions),
            phase="verifying",
            started_at=datetime.now(),
        )
        self._cancel_event.clear()
        self._pause_event.set()
        self._notify_progress()

        # Phase 1: Verify files exist
        logger.info(f"Verifying {len(self.pending_actions)} files...")
        valid_actions = []
        for action in self.pending_actions:
            if self._cancel_event.is_set():
                self.progress.is_cancelled = True
                break

            # Wait if paused
            self._pause_event.wait()

            if os.path.exists(action.source_path):
                # Get file size if not set
                if action.file_size is None:
                    with contextlib.suppress(Exception):
                        action.file_size = os.path.getsize(action.source_path)
                valid_actions.append(action)
            else:
                results.append(ActionResult(
                    action=action,
                    status=ActionStatus.FAILED,
                    error_message="File not found",
                ))
                self.progress.failed += 1

        # Phase 2: Execute operations
        self.progress.phase = "executing"
        self.progress.total_files = len(valid_actions)
        self._notify_progress()

        for action in valid_actions:
            if self._cancel_event.is_set():
                self.progress.is_cancelled = True
                # Mark remaining as cancelled
                results.append(ActionResult(
                    action=action,
                    status=ActionStatus.CANCELLED,
                ))
                continue

            # Wait if paused
            self._pause_event.wait()

            self.progress.current_file = action.source_path
            self._notify_progress()

            # Execute based on type
            result = self._execute_single(action, confirm_delete)
            results.append(result)

            # Update progress
            self.progress.completed_files += 1
            if action.file_size:
                self.progress.completed_bytes += action.file_size

            if result.status == ActionStatus.SUCCESS:
                self.progress.successful += 1
            elif result.status == ActionStatus.FAILED:
                self.progress.failed += 1

            self._notify_progress()

        # Clear pending
        self.pending_actions.clear()

        self.progress.phase = "complete"
        self.progress.current_file = ""
        self._notify_progress()

        logger.info(
            f"Batch complete: {self.progress.successful} successful, "
            f"{self.progress.failed} failed, {self.progress.skipped} skipped"
        )

        return results

    def _execute_single(
        self,
        action: PendingAction,
        confirm_delete: bool,
    ) -> ActionResult:
        """Execute a single action."""
        try:
            if action.action_type == ActionType.QUARANTINE:
                return self.quarantine(action.source_path, action.file_hash)
            elif action.action_type == ActionType.TRASH:
                return self.send_to_trash(action.source_path)
            elif action.action_type == ActionType.DELETE:
                return self.delete_permanently(action.source_path, confirm=confirm_delete)
            elif action.action_type == ActionType.COPY:
                if not action.dest_path:
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Copy requires destination path",
                    )
                return self.copy_file(action.source_path, action.dest_path)
            elif action.action_type == ActionType.MOVE:
                if not action.dest_path:
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Move requires destination path",
                    )
                return self.move_file(action.source_path, action.dest_path)
            elif action.action_type == ActionType.LINK:
                if not action.dest_path:
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Link requires destination path",
                    )
                link_type = (action.metadata or {}).get("link_type", "hard")
                if link_type == "symbolic":
                    return self.create_symbolic_link(action.source_path, action.dest_path)
                else:
                    return self.create_hard_link(action.source_path, action.dest_path)
            else:
                return ActionResult(
                    action=action,
                    status=ActionStatus.FAILED,
                    error_message=f"Unknown action type: {action.action_type}",
                )
        except Exception as e:
            logger.error(f"Unexpected error executing action: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
            )

    def pause(self) -> None:
        """Pause execution."""
        self._pause_event.clear()
        self.progress.is_paused = True
        logger.info("Execution paused")

    def resume(self) -> None:
        """Resume execution."""
        self._pause_event.set()
        self.progress.is_paused = False
        logger.info("Execution resumed")

    def cancel(self) -> None:
        """Cancel execution."""
        self._cancel_event.set()
        self._pause_event.set()  # Unpause to allow loop to exit
        logger.info("Execution cancelled")

    # === Undo Operations ===

    def undo_action(self, log_entry_id: int) -> ActionResult:
        """Undo a logged action.

        Args:
            log_entry_id: ID of the action log entry to undo

        Returns:
            ActionResult with status
        """
        start_time = time.time()

        # Get the log entry
        entry = self.db.get_action_log_by_id(log_entry_id)
        if not entry:
            return ActionResult(
                action=PendingAction(ActionType.RESTORE, ""),
                status=ActionStatus.FAILED,
                error_message="Action log entry not found",
                elapsed_seconds=time.time() - start_time,
            )

        if not entry.reversible:
            return ActionResult(
                action=PendingAction(entry.action_type, entry.source_path),
                status=ActionStatus.FAILED,
                error_message="This action is not reversible",
                elapsed_seconds=time.time() - start_time,
            )

        if entry.reversed:
            return ActionResult(
                action=PendingAction(entry.action_type, entry.source_path),
                status=ActionStatus.FAILED,
                error_message="This action has already been undone",
                elapsed_seconds=time.time() - start_time,
            )

        # Perform undo based on action type
        action = PendingAction(
            action_type=ActionType.RESTORE,
            source_path=entry.dest_path or "",
            dest_path=entry.source_path,
        )

        try:
            if entry.action_type == ActionType.QUARANTINE:
                # Move from quarantine back to original location
                if not entry.dest_path or not os.path.exists(entry.dest_path):
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Quarantined file no longer exists",
                        elapsed_seconds=time.time() - start_time,
                    )

                # Create original directory if needed
                orig_dir = os.path.dirname(entry.source_path)
                if orig_dir:
                    self._ensure_directory(orig_dir)

                if not self.dry_run:
                    shutil.move(entry.dest_path, entry.source_path)
                    self.db.mark_action_reversed(log_entry_id)

                logger.info(f"Restored from quarantine: {entry.source_path}")

            elif entry.action_type == ActionType.MOVE:
                # Move back to original location
                if not entry.dest_path or not os.path.exists(entry.dest_path):
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Moved file no longer exists at destination",
                        elapsed_seconds=time.time() - start_time,
                    )

                orig_dir = os.path.dirname(entry.source_path)
                if orig_dir:
                    self._ensure_directory(orig_dir)

                if not self.dry_run:
                    shutil.move(entry.dest_path, entry.source_path)
                    self.db.mark_action_reversed(log_entry_id)

                logger.info(f"Undid move: {entry.source_path}")

            elif entry.action_type == ActionType.COPY:
                # Delete the copy
                if not entry.dest_path or not os.path.exists(entry.dest_path):
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Copied file no longer exists",
                        elapsed_seconds=time.time() - start_time,
                    )

                if not self.dry_run:
                    os.remove(entry.dest_path)
                    self.db.mark_action_reversed(log_entry_id)

                logger.info(f"Undid copy: removed {entry.dest_path}")

            elif entry.action_type == ActionType.LINK:
                # Remove the link
                if not entry.dest_path or not os.path.exists(entry.dest_path):
                    return ActionResult(
                        action=action,
                        status=ActionStatus.FAILED,
                        error_message="Link no longer exists",
                        elapsed_seconds=time.time() - start_time,
                    )

                if not self.dry_run:
                    os.remove(entry.dest_path)
                    self.db.mark_action_reversed(log_entry_id)

                logger.info(f"Undid link: removed {entry.dest_path}")

            elif entry.action_type == ActionType.TRASH:
                # Cannot programmatically restore from system trash
                return ActionResult(
                    action=action,
                    status=ActionStatus.FAILED,
                    error_message="Please restore from Recycle Bin manually",
                    elapsed_seconds=time.time() - start_time,
                )

            else:
                return ActionResult(
                    action=action,
                    status=ActionStatus.FAILED,
                    error_message=f"Cannot undo action type: {entry.action_type}",
                    elapsed_seconds=time.time() - start_time,
                )

            # Log the undo action
            self._log_action(
                ActionType.RESTORE,
                entry.dest_path or "",
                entry.source_path,
                entry.file_hash,
                entry.file_size,
                reversible=False,
                metadata={"undid_action_id": log_entry_id},
            )

            return ActionResult(
                action=action,
                status=ActionStatus.SUCCESS,
                elapsed_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to undo action {log_entry_id}: {e}")
            return ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def undo_batch(self, log_entry_ids: list[int]) -> list[ActionResult]:
        """Undo multiple actions.

        Args:
            log_entry_ids: List of action log IDs to undo

        Returns:
            List of ActionResults
        """
        results = []
        for entry_id in log_entry_ids:
            result = self.undo_action(entry_id)
            results.append(result)
        return results

    # === Quarantine Management ===

    def get_quarantine_stats(self) -> dict:
        """Get statistics about quarantine folder."""
        stats = {
            "total_files": 0,
            "total_size": 0,
            "by_date": {},
        }

        if not os.path.exists(self.quarantine_folder):
            return stats

        for date_folder in os.listdir(self.quarantine_folder):
            date_path = os.path.join(self.quarantine_folder, date_folder)
            if os.path.isdir(date_path):
                folder_stats = {"files": 0, "size": 0}
                for root, _, files in os.walk(date_path):
                    for f in files:
                        file_path = os.path.join(root, f)
                        try:
                            folder_stats["files"] += 1
                            folder_stats["size"] += os.path.getsize(file_path)
                        except Exception:
                            pass
                stats["by_date"][date_folder] = folder_stats
                stats["total_files"] += folder_stats["files"]
                stats["total_size"] += folder_stats["size"]

        return stats

    def empty_quarantine(
        self,
        before_date: str | None = None,
        confirm: bool = False,
    ) -> int:
        """Empty quarantine folder.

        Args:
            before_date: Only delete quarantine folders before this date (YYYY-MM-DD)
            confirm: Must be True to actually delete

        Returns:
            Number of files deleted
        """
        if not confirm:
            logger.warning("Empty quarantine called without confirm=True")
            return 0

        if not os.path.exists(self.quarantine_folder):
            return 0

        deleted_count = 0
        for date_folder in os.listdir(self.quarantine_folder):
            date_path = os.path.join(self.quarantine_folder, date_folder)
            if not os.path.isdir(date_path):
                continue

            # Check date filter
            if before_date and date_folder >= before_date:
                continue

            # Delete folder
            if not self.dry_run:
                try:
                    for _root, _, files in os.walk(date_path):
                        deleted_count += len(files)
                    shutil.rmtree(date_path)
                    logger.info(f"Emptied quarantine folder: {date_path}")
                except Exception as e:
                    logger.error(f"Failed to delete quarantine folder {date_path}: {e}")
            else:
                for _root, _, files in os.walk(date_path):
                    deleted_count += len(files)
                logger.info(f"[DRY RUN] Would empty quarantine folder: {date_path}")

        return deleted_count
