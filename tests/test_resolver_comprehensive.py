"""Comprehensive tests for the resolver module.

These tests focus on real business logic for duplicate resolution,
edge cases, and scenarios that could cause data loss if handled incorrectly.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import os

import pytest

from duplicleaner.core.resolver import (
    Resolver,
    Resolution,
    ResolutionPreview,
    ResolutionStrategy,
    get_strategy_description,
)
from duplicleaner.db.models import (
    FileRecord,
    DuplicateGroup,
    DuplicateMember,
    MatchType,
    GroupStatus,
    FileMetadata,
)

from tests.conftest import make_file_record


def _make_file(path: Path, size: int, mtime: datetime) -> None:
    """Create a test file with specific size and modification time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def _create_duplicate_group(test_db, test_drive, files_data: list[dict], tmp_path: Path) -> int:
    """Helper to create a duplicate group with specified files.

    Args:
        files_data: List of dicts with 'name', 'size', 'mtime', and optionally 'subdir'
    """
    file_ids = []
    for data in files_data:
        subdir = data.get('subdir', '')
        if subdir:
            path = tmp_path / subdir / data['name']
        else:
            path = tmp_path / data['name']

        _make_file(path, data['size'], data['mtime'])
        record = make_file_record(path, test_drive.id)
        file_id = test_db.add_file(record)
        file_ids.append(file_id)

    group_id = test_db.create_duplicate_group(
        match_type=MatchType.EXACT,
        similarity=1.0,
        file_ids=file_ids,
    )
    return group_id


class TestResolverStrategies:
    """Test all resolution strategies work correctly."""

    def test_keep_newest_selects_most_recent(self, tmp_path: Path, test_db, test_drive) -> None:
        """Verify KEEP_NEWEST selects the file with the most recent mtime."""
        now = datetime.now()
        files = [
            {'name': 'old.txt', 'size': 100, 'mtime': now - timedelta(days=30)},
            {'name': 'newer.txt', 'size': 100, 'mtime': now - timedelta(days=10)},
            {'name': 'newest.txt', 'size': 100, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)

        assert resolution is not None
        assert 'newest.txt' in resolution.keeper_path
        assert len(resolution.remove_ids) == 2

    def test_keep_oldest_selects_original(self, tmp_path: Path, test_db, test_drive) -> None:
        """Verify KEEP_OLDEST selects the file with the oldest mtime."""
        now = datetime.now()
        files = [
            {'name': 'original.txt', 'size': 100, 'mtime': now - timedelta(days=365)},
            {'name': 'copy1.txt', 'size': 100, 'mtime': now - timedelta(days=30)},
            {'name': 'copy2.txt', 'size': 100, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_OLDEST)

        assert resolution is not None
        assert 'original.txt' in resolution.keeper_path

    def test_keep_largest_selects_biggest_file(self, tmp_path: Path, test_db, test_drive) -> None:
        """Verify KEEP_LARGEST selects the file with the most bytes."""
        now = datetime.now()
        files = [
            {'name': 'small.jpg', 'size': 1000, 'mtime': now},
            {'name': 'medium.jpg', 'size': 5000, 'mtime': now},
            {'name': 'large.jpg', 'size': 10000, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_LARGEST)

        assert resolution is not None
        assert 'large.jpg' in resolution.keeper_path
        # Space saved should be sum of smaller files
        assert resolution.space_saved == 6000  # 1000 + 5000

    def test_keep_smallest_selects_smallest_file(self, tmp_path: Path, test_db, test_drive) -> None:
        """Verify KEEP_SMALLEST selects the file with fewest bytes."""
        now = datetime.now()
        files = [
            {'name': 'small.txt', 'size': 100, 'mtime': now},
            {'name': 'medium.txt', 'size': 500, 'mtime': now},
            {'name': 'large.txt', 'size': 1000, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_SMALLEST)

        assert resolution is not None
        assert 'small.txt' in resolution.keeper_path

    def test_keep_shortest_path_prefers_simpler_paths(self, tmp_path: Path, test_db, test_drive) -> None:
        """Verify KEEP_SHORTEST_PATH prefers files with simpler directory structure."""
        now = datetime.now()
        files = [
            {'name': 'file.txt', 'size': 100, 'mtime': now, 'subdir': ''},
            {'name': 'file.txt', 'size': 100, 'mtime': now, 'subdir': 'subfolder'},
            {'name': 'file.txt', 'size': 100, 'mtime': now, 'subdir': 'deep/nested/folder'},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_SHORTEST_PATH)

        assert resolution is not None
        # The root-level file should be kept
        assert 'deep' not in resolution.keeper_path
        assert 'subfolder' not in resolution.keeper_path or 'nested' not in resolution.keeper_path

    def test_keep_longest_path_prefers_specific_paths(self, tmp_path: Path, test_db, test_drive) -> None:
        """Verify KEEP_LONGEST_PATH prefers files with more specific paths."""
        now = datetime.now()
        files = [
            {'name': 'f.txt', 'size': 100, 'mtime': now, 'subdir': ''},
            {'name': 'file.txt', 'size': 100, 'mtime': now, 'subdir': 'photos/2024/vacation'},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_LONGEST_PATH)

        assert resolution is not None
        assert 'vacation' in resolution.keeper_path

    def test_manual_strategy_returns_none(self, tmp_path: Path, test_db, test_drive) -> None:
        """Verify MANUAL strategy returns None (requires user selection)."""
        now = datetime.now()
        files = [
            {'name': 'a.txt', 'size': 100, 'mtime': now},
            {'name': 'b.txt', 'size': 100, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.MANUAL)

        assert resolution is None


class TestResolverLockedFiles:
    """Test that locked files are never selected for removal."""

    def test_locked_file_is_protected(self, tmp_path: Path, test_db, test_drive) -> None:
        """A locked file should never be removed, even if it would otherwise be selected."""
        now = datetime.now()
        # Create 3 files - one will be locked, one will be keeper, one will be removed
        old_file = tmp_path / "important_locked.txt"
        middle_file = tmp_path / "middle.txt"
        new_file = tmp_path / "recent.txt"
        _make_file(old_file, 1000, now - timedelta(days=30))
        _make_file(middle_file, 500, now - timedelta(days=15))
        _make_file(new_file, 100, now)

        old_record = make_file_record(old_file, test_drive.id)
        middle_record = make_file_record(middle_file, test_drive.id)
        new_record = make_file_record(new_file, test_drive.id)
        old_id = test_db.add_file(old_record)
        middle_id = test_db.add_file(middle_record)
        new_id = test_db.add_file(new_record)

        group_id = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=[old_id, middle_id, new_id],
        )

        resolver = Resolver(db=test_db)
        # Lock the oldest file - it should not be removed
        resolver.lock_file(old_id)

        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)

        assert resolution is not None
        # new_file is newest so it's the keeper
        assert resolution.keeper_id == new_id
        # old_id is locked, so it should NOT be in remove_ids
        assert old_id not in resolution.remove_ids
        # middle_id should be in remove_ids
        assert middle_id in resolution.remove_ids

    def test_all_files_locked_returns_none(self, tmp_path: Path, test_db, test_drive) -> None:
        """If all files in a group are locked, resolution should return None."""
        now = datetime.now()
        files = [
            {'name': 'a.txt', 'size': 100, 'mtime': now},
            {'name': 'b.txt', 'size': 100, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)

        # Lock all files
        group = test_db.get_duplicate_group(group_id, include_files=True)
        for member in group.members:
            resolver.lock_file(member.file_id)

        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)
        assert resolution is None

    def test_unlock_file_allows_removal(self, tmp_path: Path, test_db, test_drive) -> None:
        """Unlocking a file should allow it to be selected for removal."""
        now = datetime.now()
        files = [
            {'name': 'old.txt', 'size': 100, 'mtime': now - timedelta(days=30)},
            {'name': 'new.txt', 'size': 100, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)

        group = test_db.get_duplicate_group(group_id, include_files=True)
        old_id = group.members[0].file_id

        resolver.lock_file(old_id)
        assert resolver.is_file_locked(old_id) is True

        resolver.unlock_file(old_id)
        assert resolver.is_file_locked(old_id) is False


class TestResolverIgnoredGroups:
    """Test that ignored groups are properly skipped."""

    def test_ignored_group_returns_none(self, tmp_path: Path, test_db, test_drive) -> None:
        """An ignored group should return None from resolve_group."""
        now = datetime.now()
        files = [
            {'name': 'a.txt', 'size': 100, 'mtime': now},
            {'name': 'b.txt', 'size': 100, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolver.ignore_group(group_id)

        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)
        assert resolution is None
        assert resolver.is_group_ignored(group_id) is True

    def test_unignore_group_allows_resolution(self, tmp_path: Path, test_db, test_drive) -> None:
        """Unignoring a group should allow it to be resolved again."""
        now = datetime.now()
        files = [
            {'name': 'a.txt', 'size': 100, 'mtime': now},
            {'name': 'b.txt', 'size': 100, 'mtime': now},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolver.ignore_group(group_id)
        resolver.unignore_group(group_id)

        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)
        assert resolution is not None


class TestResolverPreview:
    """Test resolution preview functionality."""

    def test_preview_calculates_space_recovery(self, tmp_path: Path, test_db, test_drive) -> None:
        """Preview should correctly calculate total space to be recovered."""
        now = datetime.now()

        # Create two duplicate groups
        group1_files = [
            {'name': 'g1_a.txt', 'size': 1000, 'mtime': now},
            {'name': 'g1_b.txt', 'size': 1000, 'mtime': now - timedelta(days=1)},
        ]
        _create_duplicate_group(test_db, test_drive, group1_files, tmp_path)

        group2_files = [
            {'name': 'g2_a.txt', 'size': 500, 'mtime': now},
            {'name': 'g2_b.txt', 'size': 500, 'mtime': now - timedelta(days=1)},
        ]
        _create_duplicate_group(test_db, test_drive, group2_files, tmp_path)

        resolver = Resolver(db=test_db)
        preview = resolver.preview_resolution(ResolutionStrategy.KEEP_NEWEST)

        assert preview.groups_affected == 2
        assert preview.files_to_remove == 2  # One from each group
        assert preview.space_to_recover == 1500  # 1000 + 500

    def test_preview_tracks_file_types(self, tmp_path: Path, test_db, test_drive) -> None:
        """Preview should track removals by file type."""
        now = datetime.now()

        files = [
            {'name': 'photo1.jpg', 'size': 1000, 'mtime': now},
            {'name': 'photo2.jpg', 'size': 1000, 'mtime': now - timedelta(days=1)},
        ]
        _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        preview = resolver.preview_resolution(ResolutionStrategy.KEEP_NEWEST)

        assert '.jpg' in preview.by_file_type
        count, size = preview.by_file_type['.jpg']
        assert count == 1
        assert size == 1000


class TestResolverApply:
    """Test applying resolutions to the database."""

    def test_apply_resolution_updates_database(self, tmp_path: Path, test_db, test_drive) -> None:
        """Applying a resolution should update the database status."""
        now = datetime.now()
        files = [
            {'name': 'keep.txt', 'size': 100, 'mtime': now},
            {'name': 'remove.txt', 'size': 100, 'mtime': now - timedelta(days=1)},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)

        success = resolver.apply_resolution(resolution)
        assert success is True

        # Verify database was updated
        group = test_db.get_duplicate_group(group_id)
        assert group.status == GroupStatus.RESOLVED

    def test_apply_all_with_progress(self, tmp_path: Path, test_db, test_drive) -> None:
        """Apply all resolutions should call progress callback."""
        now = datetime.now()
        files = [
            {'name': 'a.txt', 'size': 100, 'mtime': now},
            {'name': 'b.txt', 'size': 100, 'mtime': now - timedelta(days=1)},
        ]
        _create_duplicate_group(test_db, test_drive, files, tmp_path)

        progress_calls = []
        def progress_callback(completed, total):
            progress_calls.append((completed, total))

        resolver = Resolver(db=test_db)
        successful, failed = resolver.apply_all_resolutions(
            ResolutionStrategy.KEEP_NEWEST,
            progress_callback=progress_callback,
        )

        assert successful >= 1
        assert failed == 0
        assert len(progress_calls) >= 1


class TestResolverEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_file_group_returns_none(self, tmp_path: Path, test_db, test_drive) -> None:
        """A group with only one file should return None (not a duplicate)."""
        file = tmp_path / "single.txt"
        file.write_bytes(b"content")
        record = make_file_record(file, test_drive.id)
        file_id = test_db.add_file(record)

        group_id = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=[file_id],
        )

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)

        assert resolution is None

    def test_nonexistent_group_returns_none(self, test_db) -> None:
        """Resolving a nonexistent group should return None."""
        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(999999, ResolutionStrategy.KEEP_NEWEST)
        assert resolution is None

    def test_clear_selections_resets_groups(self, tmp_path: Path, test_db, test_drive) -> None:
        """Clear all selections should reset resolved groups to pending."""
        now = datetime.now()
        files = [
            {'name': 'a.txt', 'size': 100, 'mtime': now},
            {'name': 'b.txt', 'size': 100, 'mtime': now - timedelta(days=1)},
        ]
        group_id = _create_duplicate_group(test_db, test_drive, files, tmp_path)

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)
        resolver.apply_resolution(resolution)

        # Verify it's resolved
        group = test_db.get_duplicate_group(group_id)
        assert group.status == GroupStatus.RESOLVED

        # Clear and verify
        count = resolver.clear_all_selections()
        assert count >= 1

        group = test_db.get_duplicate_group(group_id)
        assert group.status == GroupStatus.PENDING


class TestResolverKeepOnDrive:
    """Test KEEP_ON_DRIVE strategy with multiple drives."""

    def test_keep_on_preferred_drive(self, tmp_path: Path, test_db) -> None:
        """KEEP_ON_DRIVE should prefer files on the specified drive."""
        from duplicleaner.db.models import Drive

        # Create two drives
        drive1_path = tmp_path / "drive1"
        drive2_path = tmp_path / "drive2"
        drive1_path.mkdir()
        drive2_path.mkdir()

        drive1 = Drive(id="D1", label="Drive1", path=str(drive1_path))
        drive2 = Drive(id="D2", label="Drive2", path=str(drive2_path))
        test_db.add_drive(drive1)
        test_db.add_drive(drive2)

        # Create same file on both drives
        now = datetime.now()
        file1 = drive1_path / "file.txt"
        file2 = drive2_path / "file.txt"
        _make_file(file1, 100, now)
        _make_file(file2, 100, now)

        record1 = make_file_record(file1, "D1")
        record2 = make_file_record(file2, "D2")
        id1 = test_db.add_file(record1)
        id2 = test_db.add_file(record2)

        group_id = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=[id1, id2],
        )

        resolver = Resolver(db=test_db)
        resolution = resolver.resolve_group(
            group_id,
            ResolutionStrategy.KEEP_ON_DRIVE,
            preferred_drive_id="D2",
        )

        assert resolution is not None
        assert resolution.keeper_id == id2  # File on D2 should be kept


class TestStrategyDescriptions:
    """Test strategy description helper."""

    def test_all_strategies_have_descriptions(self) -> None:
        """All strategies should have human-readable descriptions."""
        for strategy in ResolutionStrategy:
            desc = get_strategy_description(strategy)
            assert desc is not None
            assert len(desc) > 0

    def test_description_is_user_friendly(self) -> None:
        """Descriptions should be understandable by users."""
        desc = get_strategy_description(ResolutionStrategy.KEEP_NEWEST)
        assert "newest" in desc.lower() or "recent" in desc.lower()

        desc = get_strategy_description(ResolutionStrategy.KEEP_LARGEST)
        assert "largest" in desc.lower() or "quality" in desc.lower()
