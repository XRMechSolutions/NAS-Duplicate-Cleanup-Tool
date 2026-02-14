"""Drive management modules for DupliCleaner.

Handles multi-drive coordination, status monitoring,
and redundancy checking.
"""

from duplicleaner.drives.manager import (
    DriveInfo,
    DriveManager,
    DriveStatus,
    SpaceInfo,
    get_unc_parts,
    is_unc_path,
    normalize_path,
)
from duplicleaner.drives.redundancy import (
    AtRiskGroup,
    BackupPlanItem,
    HashGroup,
    RedundancyChecker,
    RedundancyReport,
)

__all__ = [
    "DriveManager",
    "DriveStatus",
    "DriveInfo",
    "SpaceInfo",
    "is_unc_path",
    "normalize_path",
    "get_unc_parts",
    "RedundancyChecker",
    "RedundancyReport",
    "AtRiskGroup",
    "HashGroup",
    "BackupPlanItem",
]
