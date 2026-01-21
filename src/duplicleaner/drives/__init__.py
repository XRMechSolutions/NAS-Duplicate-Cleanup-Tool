"""Drive management modules for DupliCleaner.

Handles multi-drive coordination, status monitoring,
and redundancy checking.
"""

from duplicleaner.drives.manager import (
    DriveManager,
    DriveStatus,
    DriveInfo,
    SpaceInfo,
    is_unc_path,
    normalize_path,
    get_unc_parts,
)
from duplicleaner.drives.redundancy import (
    RedundancyChecker,
    RedundancyReport,
    AtRiskGroup,
    HashGroup,
    BackupPlanItem,
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
