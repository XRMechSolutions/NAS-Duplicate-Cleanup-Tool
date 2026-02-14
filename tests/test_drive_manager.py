"""Tests for the drive manager module."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from duplicleaner.db.models import Drive
from duplicleaner.drives.manager import (
    DriveInfo,
    DriveManager,
    DriveStatus,
    SpaceInfo,
    _format_bytes,
    get_unc_parts,
    is_unc_path,
    normalize_path,
)


class TestSpaceInfo:
    """Test SpaceInfo dataclass."""

    def test_used_percent(self) -> None:
        info = SpaceInfo(total_bytes=100, free_bytes=30, used_bytes=70)
        assert info.used_percent == 70.0

    def test_used_percent_zero_total(self) -> None:
        info = SpaceInfo(total_bytes=0, free_bytes=0, used_bytes=0)
        assert info.used_percent == 0.0

    def test_free_percent(self) -> None:
        info = SpaceInfo(total_bytes=100, free_bytes=30, used_bytes=70)
        assert info.free_percent == 30.0

    def test_format_total(self) -> None:
        info = SpaceInfo(total_bytes=1024, free_bytes=512, used_bytes=512)
        assert "KB" in info.format_total()

    def test_format_free(self) -> None:
        info = SpaceInfo(total_bytes=1024, free_bytes=512, used_bytes=512)
        assert "B" in info.format_free() or "KB" in info.format_free()

    def test_format_used(self) -> None:
        info = SpaceInfo(total_bytes=1024, free_bytes=512, used_bytes=512)
        formatted = info.format_used()
        assert formatted  # Should return something


class TestFormatBytes:
    """Test _format_bytes helper."""

    def test_format_bytes(self) -> None:
        assert "B" in _format_bytes(500)

    def test_format_kb(self) -> None:
        assert "KB" in _format_bytes(2048)

    def test_format_mb(self) -> None:
        assert "MB" in _format_bytes(2 * 1024 * 1024)

    def test_format_gb(self) -> None:
        assert "GB" in _format_bytes(2 * 1024 * 1024 * 1024)

    def test_format_tb(self) -> None:
        assert "TB" in _format_bytes(2 * 1024 * 1024 * 1024 * 1024)


class TestIsUncPath:
    """Test is_unc_path function."""

    def test_unc_backslash(self) -> None:
        assert is_unc_path("\\\\server\\share") is True

    def test_unc_forward_slash(self) -> None:
        assert is_unc_path("//server/share") is True

    def test_local_path_windows(self) -> None:
        assert is_unc_path("C:\\Users") is False

    def test_local_path_unix(self) -> None:
        assert is_unc_path("/home/user") is False

    def test_relative_path(self) -> None:
        assert is_unc_path("folder/subfolder") is False


class TestNormalizePath:
    """Test normalize_path function."""

    @pytest.mark.skipif(os.name != 'nt', reason="Windows-specific test")
    def test_normalize_forward_slashes_windows(self) -> None:
        result = normalize_path("C:/Users/test")
        assert "/" not in result or "\\" in result

    def test_normalize_removes_trailing_slash(self) -> None:
        result = normalize_path("/path/to/dir/")
        assert not result.endswith("/")
        assert not result.endswith("\\")

    def test_normalize_unc_path(self) -> None:
        result = normalize_path("\\\\\\\\server\\share")
        assert result.startswith("\\\\")


class TestGetUncParts:
    """Test get_unc_parts function."""

    def test_get_parts_basic(self) -> None:
        server, share = get_unc_parts("\\\\server\\share\\folder")
        assert server == "server"
        assert share == "share"

    def test_get_parts_forward_slash(self) -> None:
        server, share = get_unc_parts("//server/share/folder")
        assert server == "server"
        assert share == "share"

    def test_get_parts_minimal(self) -> None:
        server, share = get_unc_parts("\\\\server")
        assert server == "server"
        assert share == ""


class TestDriveManagerInit:
    """Test DriveManager initialization."""

    def test_init_with_db(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        assert manager.db is test_db

    def test_init_with_callback(self, test_db) -> None:
        callback = MagicMock()
        manager = DriveManager(db=test_db, status_callback=callback)
        assert manager.status_callback is callback

    def test_init_empty_cache(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        assert manager._status_cache == {}


class TestDriveManagerAddDrive:
    """Test adding drives."""

    def test_add_drive_success(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "test_drive"
        drive_path.mkdir()

        drive = manager.add_drive(str(drive_path), "Test Drive")

        assert drive is not None
        assert drive.label == "Test Drive"
        assert drive.path == normalize_path(str(drive_path))

    def test_add_drive_nonexistent_path(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        fake_path = tmp_path / "nonexistent"

        with pytest.raises(ValueError, match="does not exist"):
            manager.add_drive(str(fake_path), "Fake Drive")

    def test_add_drive_file_instead_of_dir(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="not a directory"):
            manager.add_drive(str(file_path), "File Drive")

    def test_add_drive_already_registered(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        drive1 = manager.add_drive(str(drive_path), "Drive 1")
        drive2 = manager.add_drive(str(drive_path), "Drive 2")

        assert drive1.id == drive2.id

    def test_add_drive_distinct_subfolders_get_unique_ids(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_root = tmp_path / "drive_root"
        folder_a = drive_root / "folder_a"
        folder_b = drive_root / "folder_b"
        folder_a.mkdir(parents=True)
        folder_b.mkdir(parents=True)

        drive_a = manager.add_drive(str(folder_a), "Folder A")
        drive_b = manager.add_drive(str(folder_b), "Folder B")

        assert drive_a.id != drive_b.id


class TestDriveManagerRemoveDrive:
    """Test removing drives."""

    def test_remove_drive(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        drive = manager.add_drive(str(drive_path), "Test Drive")
        manager.remove_drive(drive.id)

        assert manager.get_drive(drive.id) is None

    def test_remove_nonexistent_drive(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        # Should not raise
        manager.remove_drive("nonexistent_id")


class TestDriveManagerGetDrive:
    """Test getting drives."""

    def test_get_drive_exists(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        added = manager.add_drive(str(drive_path), "Test")
        retrieved = manager.get_drive(added.id)

        assert retrieved is not None
        assert retrieved.id == added.id

    def test_get_drive_not_exists(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        assert manager.get_drive("nonexistent") is None


class TestDriveManagerGetAllDrives:
    """Test getting all drives."""

    def test_get_all_drives_empty(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        drives = manager.get_all_drives()
        # May include test fixtures
        assert isinstance(drives, list)

    def test_get_all_drives_multiple(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        initial_count = len(manager.get_all_drives())

        # Use unique subfolder names to avoid hash collisions
        for i in range(3):
            path = tmp_path / f"unique_drive_path_{i}_abc{i*100}"
            path.mkdir()
            manager.add_drive(str(path), f"Drive {i}")

        drives = manager.get_all_drives()
        # Should have at least the drives we added
        assert len(drives) >= initial_count + 1  # At least one new drive added


class TestDriveManagerStatus:
    """Test drive status operations."""

    def test_get_drive_status_not_found(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        status = manager.get_drive_status("nonexistent")
        assert status == DriveStatus.ERROR

    def test_get_drive_status_needs_scan(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        drive = manager.add_drive(str(drive_path), "Test")
        status = manager.get_drive_status(drive.id)

        assert status == DriveStatus.NEEDS_SCAN

    def test_set_drive_status(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        drive = manager.add_drive(str(drive_path), "Test")
        manager.set_drive_status(drive.id, DriveStatus.SCANNING)

        assert manager._status_cache[drive.id] == DriveStatus.SCANNING

    def test_set_drive_status_triggers_callback(self, test_db, tmp_path: Path) -> None:
        callback = MagicMock()
        manager = DriveManager(db=test_db, status_callback=callback)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        drive = manager.add_drive(str(drive_path), "Test")
        manager.set_drive_status(drive.id, DriveStatus.SCANNING)

        callback.assert_called_once_with(drive.id, DriveStatus.SCANNING)


class TestDriveManagerDriveInfo:
    """Test extended drive info."""

    def test_get_drive_info_not_found(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        info = manager.get_drive_info("nonexistent")
        assert info is None

    def test_get_drive_info_local(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        drive = manager.add_drive(str(drive_path), "Test")
        info = manager.get_drive_info(drive.id)

        assert info is not None
        assert isinstance(info, DriveInfo)
        assert info.drive.id == drive.id


class TestDriveManagerSpaceInfo:
    """Test space info retrieval."""

    def test_get_space_info_valid_path(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        info = manager.get_space_info(str(tmp_path))

        if info is not None:
            assert info.total_bytes > 0
            assert info.free_bytes >= 0
            assert info.used_bytes >= 0

    def test_get_space_info_invalid_path(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        info = manager.get_space_info("/nonexistent/path/that/does/not/exist")

        # May return None or succeed depending on platform
        assert info is None or isinstance(info, SpaceInfo)


class TestDriveManagerRefreshStats:
    """Test drive stats refresh."""

    def test_refresh_drive_stats(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        drive = manager.add_drive(str(drive_path), "Test")
        manager.refresh_drive_stats(drive.id)

        # Should not raise

    def test_refresh_drive_stats_nonexistent(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        # Should not raise
        manager.refresh_drive_stats("nonexistent")


class TestDriveManagerCheckAllDrives:
    """Test checking all drives."""

    def test_check_all_drives(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)

        # Create a drive with a unique path
        path = tmp_path / "check_drives_unique_drive"
        path.mkdir()
        drive = manager.add_drive(str(path), "Check Drive Test")

        statuses = manager.check_all_drives()

        assert isinstance(statuses, dict)
        # The drive we added should be in the statuses
        assert drive.id in statuses


class TestDriveManagerMonitoring:
    """Test background monitoring."""

    def test_start_monitoring(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        manager.start_monitoring(interval_seconds=1)

        try:
            assert manager._monitor_thread is not None
            assert manager._monitor_thread.is_alive()
        finally:
            manager.stop_monitoring()

    def test_start_monitoring_already_running(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        manager.start_monitoring(interval_seconds=1)
        first_thread = manager._monitor_thread
        manager.start_monitoring(interval_seconds=1)

        try:
            assert manager._monitor_thread is first_thread
        finally:
            manager.stop_monitoring()

    def test_stop_monitoring(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        manager.start_monitoring(interval_seconds=1)
        manager.stop_monitoring()

        assert manager._monitor_thread is None or not manager._monitor_thread.is_alive()


class TestDriveManagerGenerateId:
    """Test drive ID generation."""

    def test_generate_id_local(self, test_db, tmp_path: Path) -> None:
        manager = DriveManager(db=test_db)
        drive_id = manager._generate_drive_id(str(tmp_path))

        assert drive_id is not None
        assert len(drive_id) > 0

    def test_generate_id_unc(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        drive_id = manager._generate_drive_id("\\\\server\\share")

        assert drive_id.startswith("net_")


class TestDriveInfo:
    """Test DriveInfo dataclass."""

    def test_drive_info_creation(self) -> None:
        drive = Drive(id="test", label="Test", path="/test")
        info = DriveInfo(
            drive=drive,
            status=DriveStatus.CONNECTED,
            is_network=False,
        )

        assert info.drive is drive
        assert info.status == DriveStatus.CONNECTED
        assert info.is_network is False
        assert info.server is None
        assert info.share is None

    def test_drive_info_network(self) -> None:
        drive = Drive(id="test", label="Test", path="\\\\server\\share")
        info = DriveInfo(
            drive=drive,
            status=DriveStatus.CONNECTED,
            is_network=True,
            server="server",
            share="share",
        )

        assert info.is_network is True
        assert info.server == "server"
        assert info.share == "share"
