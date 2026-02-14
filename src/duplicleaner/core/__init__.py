"""Core modules for DupliCleaner.

Contains the main business logic for scanning, hashing, comparison,
resolution, organization, and file actions.
"""

from duplicleaner.core.actions import (
    ActionEngine,
    ActionResult,
    ActionStatus,
    OperationProgress,
    PendingAction,
)
from duplicleaner.core.comparator import Comparator, CompareProgress, CompareResult, CompareState
from duplicleaner.core.hasher import Hasher, HashProgress, HashResult, HashState
from duplicleaner.core.organizer import (
    DateFormat,
    OrganizePreview,
    OrganizeProgress,
    Organizer,
    OrganizeResult,
    OrganizeSettings,
    get_exif_date,
)
from duplicleaner.core.resolver import Resolution, ResolutionPreview, ResolutionStrategy, Resolver
from duplicleaner.core.scanner import ScanMode, Scanner, ScanProgress, ScanResult, ScanState
from duplicleaner.core.versioning import ChangeEntry, VersionEntry, VersionTracker
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
