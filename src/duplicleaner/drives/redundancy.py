"""Redundancy analysis for multi-drive storage.

Generates at-risk reports and backup suggestions across drives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import fnmatch

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import FileRecord, Drive
from duplicleaner.drives.manager import DriveManager, normalize_path, DriveStatus
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HashGroup:
    """Group of files sharing the same content hash."""
    content_hash: str
    size: int
    file_count: int
    drive_count: int


@dataclass
class AtRiskGroup:
    """Group of files that exist on only one drive."""
    content_hash: str
    size: int
    drive_id: str
    files: list[FileRecord]


@dataclass
class RedundancyReport:
    """Summary of redundancy across drives."""
    total_hashed_files: int
    total_groups: int
    at_risk_groups: list[AtRiskGroup]
    redundant_groups: list[HashGroup]
    at_risk_files: int
    at_risk_size_bytes: int


@dataclass
class BackupPlanItem:
    """Suggested backup copy operation."""
    file_id: int
    source_drive_id: str
    target_drive_id: str
    source_path: str
    target_path: str
    size: int
    content_hash: str


@dataclass
class ExclusionCandidate:
    """Potential exclusion folder candidate."""
    pattern: str
    file_count: int
    total_size: int


class RedundancyChecker:
    """Compute redundancy reports and backup plans."""

    def __init__(
        self,
        db: Optional[Database] = None,
        drive_manager: Optional[DriveManager] = None,
    ) -> None:
        self.db = db or get_database()
        self.drive_manager = drive_manager or DriveManager(self.db)

    def build_report(self, limit: int = 1000) -> RedundancyReport:
        """Build redundancy report for hashed files."""
        groups = self.db.get_content_hash_groups(min_drives=1, limit=limit)
        total_groups = len(groups)

        at_risk_groups: list[AtRiskGroup] = []
        redundant_groups: list[HashGroup] = []
        at_risk_files = 0
        at_risk_size = 0

        for content_hash, size, file_count, drive_count in groups:
            if drive_count <= 1:
                files = self.db.get_files_by_hash(content_hash)
                drive_id = files[0].drive_id if files else ""
                at_risk_groups.append(
                    AtRiskGroup(
                        content_hash=content_hash,
                        size=size or 0,
                        drive_id=drive_id,
                        files=files,
                    )
                )
                at_risk_files += len(files)
                at_risk_size += (size or 0) * max(1, len(files))
            else:
                redundant_groups.append(
                    HashGroup(
                        content_hash=content_hash,
                        size=size or 0,
                        file_count=file_count,
                        drive_count=drive_count,
                    )
                )

        total_hashed_files = sum(g[2] for g in groups)

        return RedundancyReport(
            total_hashed_files=total_hashed_files,
            total_groups=total_groups,
            at_risk_groups=at_risk_groups,
            redundant_groups=redundant_groups,
            at_risk_files=at_risk_files,
            at_risk_size_bytes=at_risk_size,
        )

    def build_backup_plan(
        self,
        at_risk_groups: list[AtRiskGroup],
        target_drive_id: str,
    ) -> list[BackupPlanItem]:
        """Build a backup copy plan for at-risk files.

        Args:
            at_risk_groups: Groups of at-risk files
            target_drive_id: Drive to copy to
        """
        target_drive = self.db.get_drive(target_drive_id)
        if not target_drive:
            return []

        plan: list[BackupPlanItem] = []

        for group in at_risk_groups:
            for file in group.files:
                if file.id is None:
                    continue

                source_drive = self.db.get_drive(file.drive_id)
                if not source_drive:
                    continue

                rel_path = self._safe_relpath(file.path, source_drive.path, file.filename)
                target_path = str(Path(target_drive.path) / rel_path)

                plan.append(
                    BackupPlanItem(
                        file_id=file.id,
                        source_drive_id=file.drive_id,
                        target_drive_id=target_drive_id,
                        source_path=file.path,
                        target_path=target_path,
                        size=file.size,
                        content_hash=group.content_hash,
                    )
                )

        return plan

    def build_backup_plan_for_source(
        self,
        source_path: str,
        target_drive_ids: list[str],
        exclude_patterns: Optional[list[str]] = None,
        skip_if_hash_on_target: bool = True,
    ) -> list[BackupPlanItem]:
        """Build a backup plan for a source path and target drives."""
        source_drive = self._resolve_drive_for_path(source_path)
        if not source_drive:
            return []

        files = self.db.get_files_by_path_prefix(source_drive.id, source_path)
        if not files:
            return []

        exclude_patterns = exclude_patterns or []
        plan: list[BackupPlanItem] = []

        target_hashes: dict[str, set[str]] = {}
        for target_id in target_drive_ids:
            if self.drive_manager.get_drive_status(target_id) != DriveStatus.CONNECTED:
                continue
            if skip_if_hash_on_target:
                target_hashes[target_id] = self.db.get_hashes_for_drive(target_id)
            else:
                target_hashes[target_id] = set()

        for file in files:
            if self._is_excluded(file.path, exclude_patterns):
                continue
            if file.id is None:
                continue

            for target_id, hashes in target_hashes.items():
                if file.content_hash and file.content_hash in hashes:
                    continue

                target_drive = self.db.get_drive(target_id)
                if not target_drive:
                    continue

                rel_path = self._safe_relpath(file.path, source_drive.path, file.filename)
                target_path = str(Path(target_drive.path) / rel_path)

                plan.append(
                    BackupPlanItem(
                        file_id=file.id,
                        source_drive_id=source_drive.id,
                        target_drive_id=target_id,
                        source_path=file.path,
                        target_path=target_path,
                        size=file.size,
                        content_hash=file.content_hash or "",
                    )
                )

        return plan

    def get_exclusion_candidates(
        self,
        source_path: str,
        patterns: list[str],
    ) -> list[ExclusionCandidate]:
        """Analyze exclusions for a source path using patterns."""
        source_drive = self._resolve_drive_for_path(source_path)
        if not source_drive:
            return []

        candidates: list[ExclusionCandidate] = []
        base = normalize_path(source_path)
        if not base.endswith("\\"):
            base = base + "\\"
        for pattern in patterns:
            like_pattern = pattern.replace("*", "%").replace("/", "\\")
            count, total = self.db.get_path_stats_like(
                f"{base}{like_pattern}",
                drive_id=source_drive.id,
            )
            if count > 0:
                candidates.append(ExclusionCandidate(pattern=pattern, file_count=count, total_size=total))

        candidates.sort(key=lambda c: c.total_size, reverse=True)
        return candidates

    def _safe_relpath(self, path: str, root: str, fallback_name: str) -> str:
        """Compute relative path, falling back to filename on error."""
        try:
            rel = Path(path).resolve().relative_to(Path(root).resolve())
            if str(rel).startswith(".."):
                return fallback_name
            return str(rel)
        except Exception:
            return fallback_name

    def _resolve_drive_for_path(self, path: str) -> Optional[Drive]:
        drives = self.db.get_all_drives()
        normalized = normalize_path(path)
        best: Optional[Drive] = None
        for drive in drives:
            if normalize_path(drive.path) and normalized.startswith(normalize_path(drive.path)):
                if best is None or len(drive.path) > len(best.path):
                    best = drive
        return best

    def _is_excluded(self, path: str, patterns: list[str]) -> bool:
        normalized = path.replace("\\", "/")
        for pattern in patterns:
            if fnmatch.fnmatch(normalized, pattern.replace("\\", "/")):
                return True
        return False
