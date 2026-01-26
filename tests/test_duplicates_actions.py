"""Tests for duplicates panel action functionality.

These tests verify that:
1. ActionEngine is properly integrated with the duplicates panel
2. Keeper selection is required before removing files
3. Different action types (quarantine, trash, delete) work correctly
4. Confirmation flow works as expected
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duplicleaner.core.actions import ActionEngine, ActionStatus
from duplicleaner.db.database import Database
from duplicleaner.db.models import (
    Drive,
    FileRecord,
    DuplicateGroup,
    DuplicateMember,
    MatchType,
    GroupStatus,
)


@pytest.fixture
def populated_db(tmp_path: Path, test_db: Database) -> tuple[Database, list[Path]]:
    """Create a database with a duplicate group and actual files."""
    # Create test files
    files_dir = tmp_path / "files"
    files_dir.mkdir()

    file1 = files_dir / "photo1.jpg"
    file2 = files_dir / "photo1_copy.jpg"
    file3 = files_dir / "photo1_backup.jpg"

    for f in [file1, file2, file3]:
        f.write_bytes(b"fake image data " + f.name.encode())

    # Add drive
    drive = Drive(id="D1", label="TestDrive", path=str(files_dir))
    test_db.add_drive(drive)

    # Add file records
    records = []
    for f in [file1, file2, file3]:
        record = FileRecord(
            drive_id="D1",
            path=str(f),
            filename=f.name,
            size=f.stat().st_size,
            created=datetime.now(),
            modified=datetime.now(),
            file_type=".jpg",
            mime_type="image/jpeg",
            scan_date=datetime.now(),
        )
        test_db.add_file(record)
        records.append(record)

    # Create duplicate group
    group = DuplicateGroup(
        match_type=MatchType.EXACT,
        similarity=1.0,
        file_count=3,
        wasted_size=sum(r.size for r in records[1:]),  # All but keeper
        status=GroupStatus.PENDING,
    )
    group_id = test_db.add_duplicate_group(group)

    # Add members
    for i, record in enumerate(records):
        # Get the file ID from database
        db_file = test_db.get_file_by_path(str([file1, file2, file3][i]))
        member = DuplicateMember(
            group_id=group_id,
            file_id=db_file.id,
            is_keeper=False,
        )
        test_db.add_duplicate_member(member)

    return test_db, [file1, file2, file3]


class TestActionEngineIntegration:
    """Test ActionEngine integration with duplicate resolution."""

    def test_quarantine_removes_file(self, tmp_path: Path, test_db: Database) -> None:
        """Test that quarantine moves files to quarantine folder."""
        # Create a test file
        source = tmp_path / "duplicate.jpg"
        source.write_bytes(b"test data")
        quarantine_dir = tmp_path / "quarantine"

        engine = ActionEngine(
            db=test_db,
            quarantine_folder=str(quarantine_dir),
        )

        result = engine.quarantine(str(source))

        assert result.status == ActionStatus.SUCCESS
        assert not source.exists(), "Original file should be moved"
        assert result.action.dest_path is not None
        assert Path(result.action.dest_path).exists(), "File should exist in quarantine"

    def test_trash_removes_file(self, tmp_path: Path, test_db: Database, monkeypatch) -> None:
        """Test that send_to_trash works (with fallback to quarantine if send2trash unavailable)."""
        source = tmp_path / "duplicate.jpg"
        source.write_bytes(b"test data")
        quarantine_dir = tmp_path / "quarantine"

        engine = ActionEngine(
            db=test_db,
            quarantine_folder=str(quarantine_dir),
        )

        result = engine.send_to_trash(str(source))

        # Should succeed (either via send2trash or quarantine fallback)
        assert result.status == ActionStatus.SUCCESS
        assert not source.exists(), "Original file should be removed"

    def test_delete_requires_confirm(self, tmp_path: Path, test_db: Database) -> None:
        """Test that permanent delete requires confirmation."""
        source = tmp_path / "duplicate.jpg"
        source.write_bytes(b"test data")

        engine = ActionEngine(db=test_db)

        # Without confirm=True, should fail
        result = engine.delete_permanently(str(source), confirm=False)

        assert result.status == ActionStatus.FAILED
        assert source.exists(), "File should not be deleted without confirmation"

    def test_delete_with_confirm(self, tmp_path: Path, test_db: Database) -> None:
        """Test that permanent delete works with confirmation."""
        source = tmp_path / "duplicate.jpg"
        source.write_bytes(b"test data")

        engine = ActionEngine(db=test_db)

        result = engine.delete_permanently(str(source), confirm=True)

        assert result.status == ActionStatus.SUCCESS
        assert not source.exists(), "File should be deleted"

    def test_protected_path_rejection(self, test_db: Database) -> None:
        """Test that protected paths cannot be deleted."""
        engine = ActionEngine(db=test_db)

        # These should be detected as protected
        assert engine._is_protected_path("C:\\Windows\\System32\\file.dll")
        assert engine._is_protected_path("C:\\Program Files\\app\\file.exe")
        assert engine._is_protected_path("C:\\Program Files (x86)\\app\\file.exe")

        # These should not be protected
        assert not engine._is_protected_path("D:\\Photos\\vacation.jpg")
        assert not engine._is_protected_path("C:\\Users\\Public\\file.txt")


class TestKeeperRequirement:
    """Test that keeper selection is required before removing files."""

    def test_get_files_to_remove_requires_group_selection(self) -> None:
        """Test that a group must be selected."""
        # Mock the panel without selecting a group
        with patch("duplicleaner.ui.duplicates_panel.dpg"):
            from duplicleaner.ui.duplicates_panel import DuplicatesPanel

            # Create panel with mocked dependencies
            panel = MagicMock(spec=DuplicatesPanel)
            panel._selected_group_id = None
            panel._selected_group_ids = set()
            panel.db = MagicMock()
            panel._get_target_group_ids.return_value = []

            # Call the actual method
            result, error = DuplicatesPanel._get_files_to_remove(panel)

            assert result == []
            assert "No pending group selected" in error

    def test_get_files_to_remove_requires_keeper(self) -> None:
        """Test that a keeper must be selected before removing files."""
        with patch("duplicleaner.ui.duplicates_panel.dpg"):
            from duplicleaner.ui.duplicates_panel import DuplicatesPanel

            # Create mock group with no keeper
            mock_group = MagicMock()
            mock_group.members = [
                MagicMock(is_keeper=False, file_id=1),
                MagicMock(is_keeper=False, file_id=2),
            ]

            panel = MagicMock(spec=DuplicatesPanel)
            panel._selected_group_id = 1
            panel._selected_group_ids = {1}
            panel.db = MagicMock()
            panel.db.get_duplicate_group.return_value = mock_group
            panel._get_target_group_ids.return_value = [1]

            result, error = DuplicatesPanel._get_files_to_remove(panel)

            assert result == []
            assert "no keeper" in error.lower()

    def test_get_files_to_remove_returns_non_keepers(self) -> None:
        """Test that only non-keeper files are returned for removal."""
        with patch("duplicleaner.ui.duplicates_panel.dpg"):
            from duplicleaner.ui.duplicates_panel import DuplicatesPanel

            # Create mock group with one keeper
            mock_group = MagicMock()
            mock_group.members = [
                MagicMock(is_keeper=True, file_id=1),   # Keeper - should not be removed
                MagicMock(is_keeper=False, file_id=2),  # Should be removed
                MagicMock(is_keeper=False, file_id=3),  # Should be removed
            ]

            panel = MagicMock(spec=DuplicatesPanel)
            panel._selected_group_id = 1
            panel._selected_group_ids = {1}
            panel.db = MagicMock()
            panel.db.get_duplicate_group.return_value = mock_group
            panel._get_target_group_ids.return_value = [1]

            result, error = DuplicatesPanel._get_files_to_remove(panel)

            assert error is None
            assert result == [2, 3]
            assert 1 not in result, "Keeper should not be in removal list"


class TestActionLogging:
    """Test that actions are properly logged."""

    def test_quarantine_creates_log_entry(self, tmp_path: Path, test_db: Database) -> None:
        """Test that quarantine operation creates an audit log entry."""
        source = tmp_path / "logged.jpg"
        source.write_bytes(b"test data")
        quarantine_dir = tmp_path / "quarantine"

        engine = ActionEngine(
            db=test_db,
            quarantine_folder=str(quarantine_dir),
        )

        result = engine.quarantine(str(source))

        assert result.log_entry_id is not None

        # Verify log entry exists in database
        log_entry = test_db.get_action_log_by_id(result.log_entry_id)
        assert log_entry is not None
        assert log_entry.source_path == str(source)
        assert log_entry.dest_path == result.action.dest_path

    def test_delete_creates_log_entry(self, tmp_path: Path, test_db: Database) -> None:
        """Test that permanent delete creates an audit log entry."""
        source = tmp_path / "deleted.jpg"
        source.write_bytes(b"test data")

        engine = ActionEngine(db=test_db)

        result = engine.delete_permanently(str(source), confirm=True)

        assert result.log_entry_id is not None


class TestDryRunMode:
    """Test dry run mode doesn't modify files."""

    def test_dry_run_quarantine_preserves_file(self, tmp_path: Path, test_db: Database) -> None:
        """Test that dry run mode doesn't actually move files."""
        source = tmp_path / "preserved.jpg"
        source.write_bytes(b"test data")
        quarantine_dir = tmp_path / "quarantine"

        engine = ActionEngine(
            db=test_db,
            quarantine_folder=str(quarantine_dir),
            dry_run=True,
        )

        result = engine.quarantine(str(source))

        assert result.status == ActionStatus.SUCCESS
        assert source.exists(), "File should still exist in dry run mode"
        assert not quarantine_dir.exists(), "Quarantine folder should not be created"

    def test_dry_run_delete_preserves_file(self, tmp_path: Path, test_db: Database) -> None:
        """Test that dry run mode doesn't delete files."""
        source = tmp_path / "preserved.jpg"
        source.write_bytes(b"test data")

        engine = ActionEngine(db=test_db, dry_run=True)

        result = engine.delete_permanently(str(source), confirm=True)

        assert result.status == ActionStatus.SUCCESS
        assert source.exists(), "File should still exist in dry run mode"
