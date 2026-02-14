"""Drive Manager for DupliCleaner.

Handles multi-drive coordination, status monitoring, and redundancy checking.
Supports local drives, external drives, and network shares (UNC paths).
"""

import ctypes
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import Drive
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class DriveStatus(Enum):
    """Current status of a drive."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    ERROR = "error"
    NEEDS_SCAN = "needs_scan"


@dataclass
class DriveInfo:
    """Extended drive information."""

    drive: Drive
    status: DriveStatus
    is_network: bool
    server: str | None = None
    share: str | None = None
    volume_label: str | None = None
    filesystem: str | None = None


@dataclass
class SpaceInfo:
    """Disk space information."""

    total_bytes: int
    free_bytes: int
    used_bytes: int

    @property
    def used_percent(self) -> float:
        """Get usage percentage."""
        if self.total_bytes > 0:
            return (self.used_bytes / self.total_bytes) * 100
        return 0.0

    @property
    def free_percent(self) -> float:
        """Get free percentage."""
        return 100.0 - self.used_percent

    def format_total(self) -> str:
        """Format total space for display."""
        return _format_bytes(self.total_bytes)

    def format_free(self) -> str:
        """Format free space for display."""
        return _format_bytes(self.free_bytes)

    def format_used(self) -> str:
        """Format used space for display."""
        return _format_bytes(self.used_bytes)


def _format_bytes(size: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


class DriveManager:
    """Manages registered drives and monitors their status."""

    def __init__(
        self,
        db: Database | None = None,
        status_callback: Callable[[str, DriveStatus], None] | None = None,
    ):
        """Initialize the drive manager.

        Args:
            db: Database instance (uses singleton if not provided)
            status_callback: Function called when drive status changes
        """
        self.db = db or get_database()
        self.status_callback = status_callback

        # Cache of drive statuses
        self._status_cache: dict[str, DriveStatus] = {}
        self._lock = threading.Lock()

        # Background monitoring
        self._monitor_thread: threading.Thread | None = None
        self._stop_monitor = threading.Event()

    def add_drive(
        self,
        path: str,
        label: str,
        _scan_now: bool = False,
    ) -> Drive:
        """Register a new drive or network share.

        Args:
            path: Path to drive or UNC path
            label: Friendly name for the drive
            scan_now: Whether to start scanning immediately

        Returns:
            Created Drive object

        Raises:
            ValueError: If path is invalid or inaccessible
        """
        # Normalize path
        path = normalize_path(path)

        # Verify path exists
        if not os.path.exists(path):
            raise ValueError(f"Path does not exist: {path}")

        if not os.path.isdir(path):
            raise ValueError(f"Path is not a directory: {path}")

        # Generate unique ID
        drive_id = self._generate_drive_id(path)

        # Check if already registered
        existing = self.db.get_drive(drive_id)
        if existing:
            logger.info(f"Drive already registered: {label}")
            return existing

        # Detect if network drive
        is_network = is_unc_path(path)

        # Get space info
        space = self.get_space_info(path)

        # Create drive object
        drive = Drive(
            id=drive_id,
            label=label,
            path=path,
            total_space=space.total_bytes if space else None,
            free_space=space.free_bytes if space else None,
            file_count=0,
            is_network=is_network,
            created_at=datetime.now(),
        )

        # Save to database
        self.db.add_drive(drive)
        logger.info(f"Registered drive: {label} ({path})")

        # Update status cache
        self._status_cache[drive_id] = DriveStatus.NEEDS_SCAN

        return drive

    def remove_drive(self, drive_id: str) -> None:
        """Remove a drive from the registry.

        Args:
            drive_id: Drive ID to remove

        Note: This removes all scan data for the drive but does NOT
        delete any files on the drive itself.
        """
        drive = self.db.get_drive(drive_id)
        if drive:
            self.db.remove_drive(drive_id)
            self._status_cache.pop(drive_id, None)
            logger.info(f"Removed drive: {drive.label}")
        else:
            logger.warning(f"Drive not found: {drive_id}")

    def remap_drive_path(self, drive_id: str, new_path: str) -> int:
        """Remap a drive's root path to a new location.

        Updates the drive path and all associated file paths in the database.
        Use this when files have been moved to a new location (e.g., from
        a local drive to a NAS) and the stored paths are no longer valid.

        Args:
            drive_id: Drive ID to remap
            new_path: New root path for the drive

        Returns:
            Number of file records updated

        Raises:
            ValueError: If drive not found, path invalid, or path not a directory
        """
        drive = self.db.get_drive(drive_id)
        if not drive:
            raise ValueError(f"Drive not found: {drive_id}")

        new_path = normalize_path(new_path)

        if not os.path.exists(new_path):
            raise ValueError(f"Path does not exist: {new_path}")

        if not os.path.isdir(new_path):
            raise ValueError(f"Path is not a directory: {new_path}")

        old_path = drive.path
        count = self.db.remap_drive_path(drive_id, old_path, new_path)

        self._status_cache[drive_id] = DriveStatus.CONNECTED
        logger.info(
            f"Remapped drive '{drive.label}': {old_path} -> {new_path} "
            f"({count} files updated)"
        )
        return count

    def get_drive(self, drive_id: str) -> Drive | None:
        """Get a drive by ID.

        Args:
            drive_id: Drive ID

        Returns:
            Drive object or None
        """
        return self.db.get_drive(drive_id)

    def get_all_drives(self) -> list[Drive]:
        """Get all registered drives.

        Returns:
            List of Drive objects
        """
        return self.db.get_all_drives()

    def get_drive_info(self, drive_id: str) -> DriveInfo | None:
        """Get extended information about a drive.

        Args:
            drive_id: Drive ID

        Returns:
            DriveInfo object or None
        """
        drive = self.db.get_drive(drive_id)
        if not drive:
            return None

        status = self.get_drive_status(drive_id)
        is_network = is_unc_path(drive.path)

        info = DriveInfo(
            drive=drive,
            status=status,
            is_network=is_network,
        )

        if is_network:
            info.server, info.share = get_unc_parts(drive.path)
        else:
            # Try to get volume info for local drives
            volume_info = self._get_volume_info(drive.path)
            if volume_info:
                info.volume_label, info.filesystem = volume_info

        return info

    def get_drive_status(self, drive_id: str) -> DriveStatus:
        """Get the current status of a drive.

        Args:
            drive_id: Drive ID

        Returns:
            DriveStatus enum value
        """
        drive = self.db.get_drive(drive_id)
        if not drive:
            return DriveStatus.ERROR

        # Check cache first
        if drive_id in self._status_cache:
            cached = self._status_cache[drive_id]
            if cached == DriveStatus.SCANNING:
                return cached

        # Check if accessible
        if not os.path.exists(drive.path):
            self._status_cache[drive_id] = DriveStatus.DISCONNECTED
            return DriveStatus.DISCONNECTED

        # Check if never scanned
        if drive.last_scan is None:
            self._status_cache[drive_id] = DriveStatus.NEEDS_SCAN
            return DriveStatus.NEEDS_SCAN

        self._status_cache[drive_id] = DriveStatus.CONNECTED
        return DriveStatus.CONNECTED

    def set_drive_status(self, drive_id: str, status: DriveStatus) -> None:
        """Set the status of a drive (for scanning operations).

        Args:
            drive_id: Drive ID
            status: New status
        """
        with self._lock:
            old_status = self._status_cache.get(drive_id)
            self._status_cache[drive_id] = status

            if old_status != status and self.status_callback:
                self.status_callback(drive_id, status)

    def get_space_info(self, path: str) -> SpaceInfo | None:
        """Get disk space information for a path.

        Args:
            path: Path to check

        Returns:
            SpaceInfo object or None on error
        """
        try:
            if os.name == 'nt':
                # Windows
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)

                result = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(path),
                    None,
                    ctypes.pointer(total_bytes),
                    ctypes.pointer(free_bytes)
                )

                if result:
                    return SpaceInfo(
                        total_bytes=total_bytes.value,
                        free_bytes=free_bytes.value,
                        used_bytes=total_bytes.value - free_bytes.value,
                    )
            else:
                # Unix
                stat = os.statvfs(path)
                total = stat.f_blocks * stat.f_frsize
                free = stat.f_available * stat.f_frsize
                return SpaceInfo(
                    total_bytes=total,
                    free_bytes=free,
                    used_bytes=total - free,
                )

        except (OSError, AttributeError) as e:
            logger.warning(f"Could not get space info for {path}: {e}")

        return None

    def refresh_drive_stats(self, drive_id: str) -> None:
        """Refresh space and file statistics for a drive.

        Args:
            drive_id: Drive ID to refresh
        """
        drive = self.db.get_drive(drive_id)
        if not drive:
            return

        space = self.get_space_info(drive.path)
        if space:
            file_count = self.db.get_file_count(drive_id)
            self.db.update_drive_stats(
                drive_id,
                total_space=space.total_bytes,
                free_space=space.free_bytes,
                file_count=file_count,
            )
            logger.debug(f"Refreshed stats for {drive.label}")

    def check_all_drives(self) -> dict[str, DriveStatus]:
        """Check status of all registered drives.

        Returns:
            Dict mapping drive ID to status
        """
        statuses = {}
        for drive in self.get_all_drives():
            statuses[drive.id] = self.get_drive_status(drive.id)
        return statuses

    def start_monitoring(self, interval_seconds: int = 30) -> None:
        """Start background monitoring of drive status.

        Args:
            interval_seconds: How often to check drive status
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Monitoring already running")
            return

        self._stop_monitor.clear()

        def monitor_loop():
            while not self._stop_monitor.is_set():
                try:
                    for drive in self.get_all_drives():
                        old_status = self._status_cache.get(drive.id)
                        new_status = self.get_drive_status(drive.id)

                        if old_status != new_status:
                            logger.info(f"Drive {drive.label} status changed: "
                                       f"{old_status} -> {new_status}")
                            if self.status_callback:
                                self.status_callback(drive.id, new_status)

                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}")

                self._stop_monitor.wait(interval_seconds)

        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Started drive monitoring")

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None
        logger.info("Stopped drive monitoring")

    def _generate_drive_id(self, path: str) -> str:
        """Generate a unique ID for a drive.

        Args:
            path: Drive path

        Returns:
            Unique ID string
        """
        normalized = normalize_path(path)
        if is_unc_path(normalized):
            # For network drives, use normalized path as ID
            return f"net_{hash(normalized.lower()) & 0xFFFFFFFF:08x}"

        # For local drives, try to get volume serial number
        serial: int | None = None
        if os.name == 'nt':
            serial = self._get_volume_serial(normalized)

        # Root paths stay volume-based; subfolders get a unique path suffix
        if serial is not None:
            if self._is_root_path(normalized):
                return f"vol_{serial:08x}"
            path_hash = hash(normalized.lower()) & 0xFFFFFFFF
            return f"vol_{serial:08x}_{path_hash:08x}"

        # Fallback to path-based ID
        return f"loc_{hash(normalized.lower()) & 0xFFFFFFFF:08x}"

    def _is_root_path(self, path: str) -> bool:
        """Return True if the path is a root drive path."""
        normalized = normalize_path(path)
        if os.name == 'nt' and len(normalized) >= 2 and normalized[1] == ":":
            return normalized.rstrip("\\") == normalized[:2]
        return normalized == normalized.rstrip("\\/")

    def _get_volume_serial(self, path: str) -> int | None:
        """Get the volume serial number for a Windows drive.

        Args:
            path: Drive path

        Returns:
            Serial number or None
        """
        if os.name != 'nt':
            return None

        try:
            # Get root path
            root = path[:3] if len(path) >= 2 and path[1] == ':' else path

            serial = ctypes.c_uint32()
            result = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root),
                None, 0,  # Volume name buffer
                ctypes.pointer(serial),  # Serial number
                None, None, None, 0  # Other params
            )

            if result:
                return serial.value

        except Exception as e:
            logger.debug(f"Could not get volume serial for {path}: {e}")

        return None

    def _get_volume_info(self, path: str) -> tuple[str, str] | None:
        """Get volume label and filesystem type for a Windows drive.

        Args:
            path: Drive path

        Returns:
            Tuple of (volume_label, filesystem) or None
        """
        if os.name != 'nt':
            return None

        try:
            # Get root path
            root = path[:3] if len(path) >= 2 and path[1] == ':' else path

            volume_name = ctypes.create_unicode_buffer(256)
            filesystem = ctypes.create_unicode_buffer(256)

            result = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root),
                volume_name, 256,
                None,  # Serial number
                None, None,  # Max component length, flags
                filesystem, 256
            )

            if result:
                return (volume_name.value, filesystem.value)

        except Exception as e:
            logger.debug(f"Could not get volume info for {path}: {e}")

        return None


def is_unc_path(path: str) -> bool:
    """Check if a path is a UNC network path.

    Args:
        path: Path to check

    Returns:
        True if UNC path
    """
    return path.startswith('\\\\') or path.startswith('//')


def normalize_path(path: str) -> str:
    """Normalize a path for consistent storage and comparison.

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

    # Normalize UNC paths
    if path.startswith('\\\\'):
        # Ensure consistent double backslash
        path = '\\\\' + path.lstrip('\\')

    return path


def get_unc_parts(path: str) -> tuple[str, str]:
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


def resolve_drive_letter_to_unc(drive_letter: str) -> str | None:
    """Resolve a mapped drive letter to its UNC path.

    Args:
        drive_letter: Drive letter (e.g., "Z:" or "Z")

    Returns:
        UNC path or None if not a mapped drive
    """
    if os.name != 'nt':
        return None

    # Normalize drive letter
    if len(drive_letter) == 1:
        drive_letter = drive_letter + ":"
    elif len(drive_letter) > 2:
        drive_letter = drive_letter[:2]

    drive_letter = drive_letter.upper()

    try:
        buffer = ctypes.create_unicode_buffer(512)
        size = ctypes.c_uint32(512)

        result = ctypes.windll.mpr.WNetGetConnectionW(
            ctypes.c_wchar_p(drive_letter),
            buffer,
            ctypes.pointer(size)
        )

        if result == 0:  # NO_ERROR
            return buffer.value

    except Exception as e:
        logger.debug(f"Could not resolve drive letter {drive_letter}: {e}")

    return None
