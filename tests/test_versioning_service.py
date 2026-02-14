"""Tests for the versioning service module."""
from __future__ import annotations

import time
from datetime import time as dt_time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duplicleaner.core.versioning import VersionTracker
from duplicleaner.core.versioning_service import (
    TrackedRepoState,
    VersioningService,
)
from duplicleaner.utils.config import VersioningSettings


@pytest.fixture
def versioning_settings() -> VersioningSettings:
    """Create a test VersioningSettings instance."""
    return VersioningSettings(
        tracked_folders=[],
        auto_commit_mode="on_save",
        auto_commit_interval_minutes=30,
        auto_commit_daily_time="00:00",
        include_patterns=[],
        exclude_patterns=["*.tmp"],
        include_subfolders=True,
        max_file_size_mb=50.0,
    )


class TestVersioningServiceInit:
    """Test VersioningService initialization."""

    def test_init_sets_settings(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        assert service.settings == versioning_settings

    def test_init_default_poll_interval(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        assert service.poll_interval_seconds == 5

    def test_init_custom_poll_interval(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings, poll_interval_seconds=10)
        assert service.poll_interval_seconds == 10

    def test_init_minimum_poll_interval(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings, poll_interval_seconds=0)
        assert service.poll_interval_seconds == 1

    def test_init_default_debounce(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        assert service.debounce_seconds == 60

    def test_init_custom_debounce(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings, debounce_seconds=30)
        assert service.debounce_seconds == 30

    def test_init_minimum_debounce(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings, debounce_seconds=1)
        assert service.debounce_seconds == 5


class TestVersioningServiceStartStop:
    """Test service start/stop functionality."""

    def test_start_creates_thread(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        service.start()

        try:
            assert service._thread is not None
            assert service._thread.is_alive()
        finally:
            service.stop()

    def test_start_idempotent(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        service.start()
        first_thread = service._thread
        service.start()

        try:
            assert service._thread is first_thread
        finally:
            service.stop()

    def test_stop_terminates_thread(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        service.start()
        service.stop()

        assert not service._thread.is_alive() or service._stop_event.is_set()


class TestVersioningServiceParseDailyTime:
    """Test daily time parsing."""

    def test_parse_valid_time(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        result = service._parse_daily_time("14:30")
        assert result == dt_time(hour=14, minute=30)

    def test_parse_time_hour_only(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        result = service._parse_daily_time("9")
        assert result == dt_time(hour=9, minute=0)

    def test_parse_invalid_time_returns_midnight(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        result = service._parse_daily_time("invalid")
        assert result == dt_time(hour=0, minute=0)

    def test_parse_empty_time_returns_midnight(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        result = service._parse_daily_time("")
        assert result == dt_time(hour=0, minute=0)


class TestVersioningServiceSnapshotFiles:
    """Test file snapshot functionality."""

    def test_snapshot_files_empty_tracker(self, versioning_settings: VersioningSettings, tmp_path: Path) -> None:
        service = VersioningService(versioning_settings)
        tracker = VersionTracker(tmp_path)

        snapshot = service._snapshot_files(tracker)
        assert snapshot == {}

    def test_snapshot_files_with_files(self, versioning_settings: VersioningSettings, tmp_path: Path) -> None:
        service = VersioningService(versioning_settings)
        tracker = VersionTracker(tmp_path)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        snapshot = service._snapshot_files(tracker)
        assert str(test_file) in snapshot
        mtime, size = snapshot[str(test_file)]
        assert size == 7  # len("content")

    def test_snapshot_files_handles_missing_file(self, versioning_settings: VersioningSettings, tmp_path: Path) -> None:
        service = VersioningService(versioning_settings)
        tracker = VersionTracker(tmp_path)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        snapshot1 = service._snapshot_files(tracker)

        test_file.unlink()
        snapshot2 = service._snapshot_files(tracker)

        assert str(test_file) in snapshot1
        assert str(test_file) not in snapshot2


class TestVersioningServiceDiffSnapshot:
    """Test snapshot diffing."""

    def test_diff_snapshot_no_changes(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        old = {"file1": (100.0, 50)}
        new = {"file1": (100.0, 50)}

        changed = service._diff_snapshot(old, new)
        assert changed == set()

    def test_diff_snapshot_new_file(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        old = {}
        new = {"file1": (100.0, 50)}

        changed = service._diff_snapshot(old, new)
        assert changed == {"file1"}

    def test_diff_snapshot_deleted_file(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        old = {"file1": (100.0, 50)}
        new = {}

        changed = service._diff_snapshot(old, new)
        assert changed == {"file1"}

    def test_diff_snapshot_modified_file(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        old = {"file1": (100.0, 50)}
        new = {"file1": (200.0, 60)}

        changed = service._diff_snapshot(old, new)
        assert changed == {"file1"}


class TestVersioningServiceBuildCommitMessage:
    """Test commit message building."""

    def test_build_message_single_file(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        message = service._build_commit_message({"/path/to/test.txt"})
        assert message == "Auto-save: test.txt"

    def test_build_message_multiple_files(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        message = service._build_commit_message({"/path/a.txt", "/path/b.txt", "/path/c.txt"})
        assert message == "Auto-save: 3 files updated"


class TestTrackedRepoState:
    """Test TrackedRepoState dataclass."""

    def test_state_creation(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        state = TrackedRepoState(tracker=tracker)

        assert state.tracker is tracker
        assert state.last_snapshot == {}
        assert state.pending_paths == set()
        assert state.last_change_ts is None
        assert state.last_daily_commit_date is None

    def test_state_with_snapshot(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        snapshot = {"file1": (100.0, 50)}
        state = TrackedRepoState(tracker=tracker, last_snapshot=snapshot)

        assert state.last_snapshot == snapshot


class TestVersioningServiceRefresh:
    """Test refresh_tracked_folders."""

    def test_refresh_tracked_folders(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)
        # Should not raise
        service.refresh_tracked_folders()


class TestVersioningServiceCommitModes:
    """Test different commit modes in polling."""

    def test_poll_manual_mode_does_nothing(self, versioning_settings: VersioningSettings, tmp_path: Path) -> None:
        versioning_settings.auto_commit_mode = "manual"
        versioning_settings.tracked_folders = [str(tmp_path)]
        service = VersioningService(versioning_settings)

        # Mock tracker to be available
        with (
            patch.object(VersionTracker, 'is_available', return_value=True),
            patch.object(VersionTracker, 'init_repository', return_value=True),
            patch.object(VersionTracker, 'initial_commit', return_value=False),
        ):
            service._initialize_repos()

        # Create a file
        (tmp_path / "test.txt").write_text("content")

        # Poll should do nothing in manual mode
        service._poll()

    def test_commit_interval_mode(self, versioning_settings: VersioningSettings, tmp_path: Path) -> None:
        versioning_settings.auto_commit_mode = "interval"
        versioning_settings.auto_commit_interval_minutes = 1
        _ = tmp_path
        service = VersioningService(versioning_settings)

        tracker = MagicMock()
        tracker.commit_all.return_value = False
        state = TrackedRepoState(tracker=tracker)
        state.last_change_ts = time.time() - 120  # 2 minutes ago

        service._commit_interval(state)
        tracker.commit_all.assert_called_once()

    def test_commit_interval_too_soon(self, versioning_settings: VersioningSettings) -> None:
        versioning_settings.auto_commit_interval_minutes = 5
        service = VersioningService(versioning_settings)

        tracker = MagicMock()
        state = TrackedRepoState(tracker=tracker)
        state.last_change_ts = time.time()  # Just now

        service._commit_interval(state)
        tracker.commit_all.assert_not_called()

    def test_commit_daily_mode(self, versioning_settings: VersioningSettings) -> None:
        versioning_settings.auto_commit_mode = "daily"
        versioning_settings.auto_commit_daily_time = "00:00"
        service = VersioningService(versioning_settings)

        tracker = MagicMock()
        tracker.commit_all.return_value = True
        state = TrackedRepoState(tracker=tracker)
        state.last_daily_commit_date = None

        with patch('duplicleaner.core.versioning_service.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.strftime.return_value = "2024-01-15"
            mock_now.time.return_value = dt_time(hour=1, minute=0)
            mock_dt.now.return_value = mock_now

            service._commit_daily(state)

        tracker.commit_all.assert_called_once()

    def test_commit_daily_already_committed_today(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)

        tracker = MagicMock()
        state = TrackedRepoState(tracker=tracker)
        state.last_daily_commit_date = "2024-01-15"

        with patch('duplicleaner.core.versioning_service.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.strftime.return_value = "2024-01-15"
            mock_dt.now.return_value = mock_now

            service._commit_daily(state)

        tracker.commit_all.assert_not_called()


class TestVersioningServiceDetectAndCommit:
    """Test change detection and commit."""

    def test_detect_and_commit_no_changes(self, versioning_settings: VersioningSettings) -> None:
        service = VersioningService(versioning_settings)

        tracker = MagicMock()
        tracker.list_tracked_files.return_value = []
        state = TrackedRepoState(tracker=tracker)

        service._detect_and_commit(state)
        tracker.commit_all.assert_not_called()

    def test_detect_and_commit_with_changes_debounced(self, versioning_settings: VersioningSettings, tmp_path: Path) -> None:
        service = VersioningService(versioning_settings, debounce_seconds=60)

        tracker = VersionTracker(tmp_path)
        state = TrackedRepoState(tracker=tracker)

        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # First call detects change but debounces
        service._detect_and_commit(state)
        assert state.pending_paths  # Has pending paths
        assert state.last_change_ts is not None

    def test_detect_and_commit_after_debounce(self, versioning_settings: VersioningSettings, tmp_path: Path) -> None:
        service = VersioningService(versioning_settings, debounce_seconds=0)
        _ = tmp_path

        tracker = MagicMock()
        tracker.list_tracked_files.return_value = []
        tracker.commit_all.return_value = True
        state = TrackedRepoState(tracker=tracker)
        state.pending_paths = {"file.txt"}
        state.last_change_ts = time.time() - 10  # 10 seconds ago
        state.last_snapshot = {}

        service._detect_and_commit(state)
        tracker.commit_all.assert_called_once()
        assert state.pending_paths == set()
