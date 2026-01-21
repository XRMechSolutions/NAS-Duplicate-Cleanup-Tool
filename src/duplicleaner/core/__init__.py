"""Core modules for DupliCleaner.

Contains the main business logic for scanning, hashing, comparison,
resolution, organization, and file actions.
"""

from duplicleaner.core.scanner import Scanner, ScanMode, ScanState, ScanProgress, ScanResult
from duplicleaner.core.hasher import Hasher, HashState, HashProgress, HashResult
from duplicleaner.core.comparator import Comparator, CompareState, CompareProgress, CompareResult
from duplicleaner.core.resolver import Resolver, ResolutionStrategy, Resolution, ResolutionPreview
from duplicleaner.core.organizer import (
    Organizer,
    OrganizeSettings,
    OrganizePreview,
    OrganizeProgress,
    OrganizeResult,
    DateFormat,
    get_exif_date,
)
from duplicleaner.core.actions import (
    ActionEngine,
    ActionStatus,
    ActionResult,
    PendingAction,
    OperationProgress,
)
from duplicleaner.core.versioning import VersionTracker, VersionEntry, ChangeEntry
from duplicleaner.core.versioning_service import VersioningService

__all__ = [
    "Scanner",
    "ScanMode",
    "ScanState",
    "ScanProgress",
    "ScanResult",
    "Hasher",
    "HashState",
    "HashProgress",
    "HashResult",
    "Comparator",
    "CompareState",
    "CompareProgress",
    "CompareResult",
    "Resolver",
    "ResolutionStrategy",
    "Resolution",
    "ResolutionPreview",
    "Organizer",
    "OrganizeSettings",
    "OrganizePreview",
    "OrganizeProgress",
    "OrganizeResult",
    "DateFormat",
    "get_exif_date",
    "ActionEngine",
    "ActionStatus",
    "ActionResult",
    "PendingAction",
    "OperationProgress",
    "VersionTracker",
    "VersionEntry",
    "ChangeEntry",
    "VersioningService",
]
