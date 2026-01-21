"""Duplicate Resolver for DupliCleaner.

Provides strategies for deciding which duplicate files to keep
and which to remove. Supports automatic selection based on various
criteria and manual override.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import (
    FileRecord,
    DuplicateGroup,
    DuplicateMember,
    GroupStatus,
)
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class ResolutionStrategy(Enum):
    """Strategy for selecting which duplicate to keep."""

    KEEP_NEWEST = "keep_newest"
    KEEP_OLDEST = "keep_oldest"
    KEEP_LARGEST = "keep_largest"
    KEEP_SMALLEST = "keep_smallest"
    KEEP_BEST_QUALITY = "keep_best_quality"
    KEEP_ON_DRIVE = "keep_on_drive"
    KEEP_SHORTEST_PATH = "keep_shortest_path"
    KEEP_LONGEST_PATH = "keep_longest_path"
    KEEP_FIRST = "keep_first"
    MANUAL = "manual"


@dataclass
class Resolution:
    """Result of resolving a duplicate group."""

    group_id: int
    keeper_id: int
    keeper_path: str
    remove_ids: list[int]
    remove_paths: list[str]
    strategy_used: ResolutionStrategy
    space_saved: int
    reason: str


@dataclass
class ResolutionPreview:
    """Preview of resolution before applying."""

    groups_affected: int = 0
    files_to_keep: int = 0
    files_to_remove: int = 0
    space_to_recover: int = 0
    by_file_type: dict[str, tuple[int, int]] = field(default_factory=dict)  # type -> (count, bytes)
    resolutions: list[Resolution] = field(default_factory=list)


class Resolver:
    """Resolves duplicate groups by selecting keepers."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the resolver.

        Args:
            db: Database instance (uses singleton if not provided)
        """
        self.db = db or get_database()

        # Locked files that should never be removed
        self._locked_files: set[int] = set()

        # Ignored groups that should be skipped
        self._ignored_groups: set[int] = set()

    def resolve_group(
        self,
        group_id: int,
        strategy: ResolutionStrategy,
        preferred_drive_id: Optional[str] = None,
    ) -> Optional[Resolution]:
        """Resolve a single duplicate group.

        Args:
            group_id: ID of the duplicate group
            strategy: Strategy to use for selection
            preferred_drive_id: Drive ID for KEEP_ON_DRIVE strategy

        Returns:
            Resolution object or None if cannot resolve
        """
        # Skip ignored groups
        if group_id in self._ignored_groups:
            logger.debug(f"Skipping ignored group {group_id}")
            return None

        # Load group with files
        group = self.db.get_duplicate_group(group_id, include_files=True)
        if not group or len(group.members) < 2:
            return None

        # Get file records
        files = [m.file for m in group.members if m.file]
        if len(files) < 2:
            return None

        # Filter out locked files from removal candidates
        removable_files = [f for f in files if f.id not in self._locked_files]
        if not removable_files:
            logger.warning(f"All files in group {group_id} are locked")
            return None

        # Select keeper based on strategy
        keeper, reason = self._select_keeper(
            files, removable_files, strategy, preferred_drive_id
        )

        if not keeper:
            return None

        # Files to remove are all non-keepers (excluding locked)
        remove_files = [f for f in removable_files if f.id != keeper.id]

        if not remove_files:
            logger.debug(f"No files to remove in group {group_id}")
            return None

        # Calculate space saved
        space_saved = sum(f.size for f in remove_files)

        return Resolution(
            group_id=group_id,
            keeper_id=keeper.id,
            keeper_path=keeper.path,
            remove_ids=[f.id for f in remove_files],
            remove_paths=[f.path for f in remove_files],
            strategy_used=strategy,
            space_saved=space_saved,
            reason=reason,
        )

    def _select_keeper(
        self,
        all_files: list[FileRecord],
        removable_files: list[FileRecord],
        strategy: ResolutionStrategy,
        preferred_drive_id: Optional[str] = None,
    ) -> tuple[Optional[FileRecord], str]:
        """Select the file to keep based on strategy.

        Args:
            all_files: All files in the group
            removable_files: Files that can be removed (not locked)
            strategy: Strategy to use
            preferred_drive_id: Drive ID for KEEP_ON_DRIVE

        Returns:
            Tuple of (keeper file, reason string)
        """
        if strategy == ResolutionStrategy.KEEP_NEWEST:
            keeper = max(all_files, key=lambda f: f.modified or datetime.min)
            return keeper, f"Newest file (modified {keeper.modified})"

        elif strategy == ResolutionStrategy.KEEP_OLDEST:
            keeper = min(all_files, key=lambda f: f.modified or datetime.max)
            return keeper, f"Oldest file (modified {keeper.modified})"

        elif strategy == ResolutionStrategy.KEEP_LARGEST:
            keeper = max(all_files, key=lambda f: f.size)
            return keeper, f"Largest file ({keeper.size:,} bytes)"

        elif strategy == ResolutionStrategy.KEEP_SMALLEST:
            keeper = min(all_files, key=lambda f: f.size)
            return keeper, f"Smallest file ({keeper.size:,} bytes)"

        elif strategy == ResolutionStrategy.KEEP_SHORTEST_PATH:
            keeper = min(all_files, key=lambda f: len(f.path))
            return keeper, f"Shortest path ({len(keeper.path)} chars)"

        elif strategy == ResolutionStrategy.KEEP_LONGEST_PATH:
            keeper = max(all_files, key=lambda f: len(f.path))
            return keeper, f"Longest path ({len(keeper.path)} chars)"

        elif strategy == ResolutionStrategy.KEEP_ON_DRIVE:
            if not preferred_drive_id:
                # Fall back to keep first
                return all_files[0], "No preferred drive specified"

            # Find file on preferred drive
            on_drive = [f for f in all_files if f.drive_id == preferred_drive_id]
            if on_drive:
                return on_drive[0], f"On preferred drive"
            else:
                # Fall back to largest if not on preferred drive
                keeper = max(all_files, key=lambda f: f.size)
                return keeper, f"Not on preferred drive, keeping largest"

        elif strategy == ResolutionStrategy.KEEP_BEST_QUALITY:
            # This would use AI quality scores from scene_analysis
            # For now, use file size as proxy (larger = higher quality)
            keeper = max(all_files, key=lambda f: f.size)
            return keeper, f"Best quality (largest file as proxy)"

        elif strategy == ResolutionStrategy.KEEP_FIRST:
            return all_files[0], "First file in list"

        else:  # MANUAL or unknown
            return None, "Manual selection required"

    def preview_resolution(
        self,
        strategy: ResolutionStrategy,
        group_ids: Optional[list[int]] = None,
        preferred_drive_id: Optional[str] = None,
    ) -> ResolutionPreview:
        """Preview what would happen with a resolution strategy.

        Args:
            strategy: Strategy to preview
            group_ids: Specific groups to preview, or None for all pending
            preferred_drive_id: Drive ID for KEEP_ON_DRIVE strategy

        Returns:
            ResolutionPreview with statistics
        """
        preview = ResolutionPreview()

        # Get groups to process
        if group_ids:
            groups = [self.db.get_duplicate_group(gid, include_files=True) for gid in group_ids]
            groups = [g for g in groups if g is not None]
        else:
            groups = self.db.get_duplicate_groups(status=GroupStatus.PENDING, limit=10000)
            # Load files for each group
            groups = [self.db.get_duplicate_group(g.id, include_files=True) for g in groups]
            groups = [g for g in groups if g is not None]

        by_type: dict[str, tuple[int, int]] = {}

        for group in groups:
            if group.id in self._ignored_groups:
                continue

            resolution = self.resolve_group(group.id, strategy, preferred_drive_id)
            if resolution:
                preview.groups_affected += 1
                preview.files_to_keep += 1
                preview.files_to_remove += len(resolution.remove_ids)
                preview.space_to_recover += resolution.space_saved
                preview.resolutions.append(resolution)

                # Track by file type
                for file_id in resolution.remove_ids:
                    file = self.db.get_file(file_id)
                    if file and file.file_type:
                        ftype = file.file_type.lower()
                        count, size = by_type.get(ftype, (0, 0))
                        by_type[ftype] = (count + 1, size + file.size)

        preview.by_file_type = by_type
        return preview

    def apply_resolution(self, resolution: Resolution) -> bool:
        """Apply a resolution to mark the keeper in the database.

        Args:
            resolution: Resolution to apply

        Returns:
            True if successful
        """
        try:
            self.db.resolve_duplicate_group(resolution.group_id, resolution.keeper_id)
            logger.info(f"Resolved group {resolution.group_id}: "
                       f"keeping {resolution.keeper_path}")
            return True
        except Exception as e:
            logger.error(f"Error applying resolution: {e}")
            return False

    def apply_all_resolutions(
        self,
        strategy: ResolutionStrategy,
        group_ids: Optional[list[int]] = None,
        preferred_drive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> tuple[int, int]:
        """Apply resolution strategy to multiple groups.

        Args:
            strategy: Strategy to apply
            group_ids: Specific groups, or None for all pending
            preferred_drive_id: Drive ID for KEEP_ON_DRIVE
            progress_callback: Called with (completed, total)

        Returns:
            Tuple of (successful, failed) counts
        """
        preview = self.preview_resolution(strategy, group_ids, preferred_drive_id)

        successful = 0
        failed = 0
        total = len(preview.resolutions)

        for i, resolution in enumerate(preview.resolutions):
            if self.apply_resolution(resolution):
                successful += 1
            else:
                failed += 1

            if progress_callback:
                progress_callback(i + 1, total)

        logger.info(f"Applied resolutions: {successful} successful, {failed} failed")
        return successful, failed

    def lock_file(self, file_id: int) -> None:
        """Lock a file so it won't be selected for removal.

        Args:
            file_id: File ID to lock
        """
        self._locked_files.add(file_id)
        logger.debug(f"Locked file {file_id}")

    def unlock_file(self, file_id: int) -> None:
        """Unlock a previously locked file.

        Args:
            file_id: File ID to unlock
        """
        self._locked_files.discard(file_id)
        logger.debug(f"Unlocked file {file_id}")

    def is_file_locked(self, file_id: int) -> bool:
        """Check if a file is locked.

        Args:
            file_id: File ID to check

        Returns:
            True if locked
        """
        return file_id in self._locked_files

    def ignore_group(self, group_id: int) -> None:
        """Ignore a duplicate group (mark as intentional duplicates).

        Args:
            group_id: Group ID to ignore
        """
        self._ignored_groups.add(group_id)
        # Also update database status
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE duplicate_groups SET status = ? WHERE id = ?",
                (GroupStatus.IGNORED.value, group_id)
            )
        logger.debug(f"Ignored group {group_id}")

    def unignore_group(self, group_id: int) -> None:
        """Unignore a previously ignored group.

        Args:
            group_id: Group ID to unignore
        """
        self._ignored_groups.discard(group_id)
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE duplicate_groups SET status = ? WHERE id = ?",
                (GroupStatus.PENDING.value, group_id)
            )
        logger.debug(f"Unignored group {group_id}")

    def is_group_ignored(self, group_id: int) -> bool:
        """Check if a group is ignored.

        Args:
            group_id: Group ID to check

        Returns:
            True if ignored
        """
        return group_id in self._ignored_groups

    def get_recommendation(
        self,
        group_id: int,
    ) -> Optional[tuple[FileRecord, list[str]]]:
        """Get AI-powered recommendation for a duplicate group.

        Considers multiple factors to suggest the best file to keep.

        Args:
            group_id: Group ID to analyze

        Returns:
            Tuple of (recommended keeper, list of reasons) or None
        """
        group = self.db.get_duplicate_group(group_id, include_files=True)
        if not group or len(group.members) < 2:
            return None

        files = [m.file for m in group.members if m.file]
        if len(files) < 2:
            return None

        # Score each file
        scores: dict[int, tuple[float, list[str]]] = {}

        for file in files:
            score = 0.0
            reasons = []

            # Size (larger is better for media)
            max_size = max(f.size for f in files)
            if file.size == max_size:
                score += 2.0
                reasons.append("Largest file (highest resolution)")

            # Date (oldest original is often best)
            oldest = min(f.modified or datetime.max for f in files)
            if file.modified == oldest:
                score += 1.0
                reasons.append("Original file (oldest)")

            # Path simplicity (shorter paths are cleaner)
            shortest_path = min(len(f.path) for f in files)
            if len(file.path) == shortest_path:
                score += 0.5
                reasons.append("Cleaner file path")

            # Check for metadata (files with EXIF are better)
            metadata = self.db.get_file_metadata(file.id)
            if metadata:
                if metadata.exif_date:
                    score += 0.5
                    reasons.append("Has EXIF date")
                if metadata.has_gps:
                    score += 0.3
                    reasons.append("Has GPS coordinates")
                if metadata.camera_make:
                    score += 0.2
                    reasons.append("Has camera info")

            # Check for quality score
            analysis = self.db.get_scene_analysis(file.id)
            if analysis and analysis.quality_score:
                score += analysis.quality_score / 10.0
                reasons.append(f"Quality score: {analysis.quality_score:.1f}")

            scores[file.id] = (score, reasons)

        # Find best file
        best_id = max(scores, key=lambda x: scores[x][0])
        best_file = next(f for f in files if f.id == best_id)
        _, reasons = scores[best_id]

        return best_file, reasons

    def clear_all_selections(self) -> int:
        """Clear all resolution selections, resetting groups to pending.

        Returns:
            Number of groups reset
        """
        with self.db.connection() as conn:
            result = conn.execute(
                "UPDATE duplicate_groups SET status = ? WHERE status = ?",
                (GroupStatus.PENDING.value, GroupStatus.RESOLVED.value)
            )
            conn.execute(
                "UPDATE duplicate_members SET is_keeper = FALSE"
            )
            count = result.rowcount

        logger.info(f"Cleared {count} resolution selections")
        return count


def get_strategy_description(strategy: ResolutionStrategy) -> str:
    """Get a human-readable description of a strategy.

    Args:
        strategy: Strategy to describe

    Returns:
        Description string
    """
    descriptions = {
        ResolutionStrategy.KEEP_NEWEST: "Keep the most recently modified file",
        ResolutionStrategy.KEEP_OLDEST: "Keep the original (oldest) file",
        ResolutionStrategy.KEEP_LARGEST: "Keep the largest file (highest quality)",
        ResolutionStrategy.KEEP_SMALLEST: "Keep the smallest file (save most space)",
        ResolutionStrategy.KEEP_BEST_QUALITY: "Keep the best quality file (AI-scored)",
        ResolutionStrategy.KEEP_ON_DRIVE: "Keep the copy on your preferred drive",
        ResolutionStrategy.KEEP_SHORTEST_PATH: "Keep the file with the simplest path",
        ResolutionStrategy.KEEP_LONGEST_PATH: "Keep the file with the most specific path",
        ResolutionStrategy.KEEP_FIRST: "Keep the first file found",
        ResolutionStrategy.MANUAL: "Choose manually for each duplicate",
    }
    return descriptions.get(strategy, "Unknown strategy")
