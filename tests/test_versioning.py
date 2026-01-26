"""Tests for the versioning module."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duplicleaner.core.versioning import (
    VersionTracker,
    VersionEntry,
    ChangeEntry,
    DEFAULT_EXCLUDE_PATTERNS,
    GIT_AVAILABLE,
)


class TestVersionTrackerInit:
    """Test VersionTracker initialization."""

    def test_init_sets_root_path(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        assert tracker.root_path == tmp_path

    def test_init_default_exclude_patterns(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        assert tracker.exclude_patterns == DEFAULT_EXCLUDE_PATTERNS

    def test_init_custom_exclude_patterns(self, tmp_path: Path) -> None:
        patterns = ["*.log", "*.tmp"]
        tracker = VersionTracker(tmp_path, exclude_patterns=patterns)
        assert tracker.exclude_patterns == patterns

    def test_init_include_patterns(self, tmp_path: Path) -> None:
        patterns = ["*.txt", "*.md"]
        tracker = VersionTracker(tmp_path, include_patterns=patterns)
        assert tracker.include_patterns == patterns

    def test_init_max_file_size(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, max_file_size_mb=10.0)
        assert tracker.max_file_size_bytes == 10 * 1024 * 1024

    def test_init_include_subfolders_default(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        assert tracker.include_subfolders is True

    def test_init_include_subfolders_disabled(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, include_subfolders=False)
        assert tracker.include_subfolders is False


class TestVersionTrackerAvailability:
    """Test VersionTracker availability checks."""

    def test_is_available_reflects_git_availability(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        assert tracker.is_available() == GIT_AVAILABLE


class TestVersionTrackerShouldTrack:
    """Test file tracking decisions."""

    def test_should_track_normal_file(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        assert tracker._should_track(test_file) is True

    def test_should_not_track_excluded_pattern(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, exclude_patterns=["*.log"])
        test_file = tmp_path / "debug.log"
        test_file.write_text("log content")

        assert tracker._should_track(test_file) is False

    def test_should_not_track_large_file(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, max_file_size_mb=0.0001)
        test_file = tmp_path / "large.bin"
        test_file.write_bytes(b"x" * 1000)

        assert tracker._should_track(test_file) is False

    def test_should_track_with_include_pattern(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, include_patterns=["*.txt"])
        txt_file = tmp_path / "doc.txt"
        txt_file.write_text("content")
        bin_file = tmp_path / "data.bin"
        bin_file.write_bytes(b"binary")

        assert tracker._should_track(txt_file) is True
        assert tracker._should_track(bin_file) is False

    def test_should_track_nonexistent_file(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        fake_file = tmp_path / "nonexistent.txt"

        assert tracker._should_track(fake_file) is False


class TestVersionTrackerListFiles:
    """Test file listing."""

    def test_list_tracked_files_empty(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        files = tracker.list_tracked_files()
        assert files == []

    def test_list_tracked_files_with_files(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        files = tracker.list_tracked_files()
        assert len(files) == 2

    def test_list_tracked_files_excludes_patterns(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, exclude_patterns=["*.log"])
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "debug.log").write_text("log")

        files = tracker.list_tracked_files()
        assert len(files) == 1
        assert files[0].name == "a.txt"

    def test_list_tracked_files_with_subfolders(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, include_subfolders=True)
        (tmp_path / "root.txt").write_text("root")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested")

        files = tracker.list_tracked_files()
        assert len(files) == 2

    def test_list_tracked_files_without_subfolders(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path, include_subfolders=False)
        (tmp_path / "root.txt").write_text("root")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested")

        files = tracker.list_tracked_files()
        assert len(files) == 1
        assert files[0].name == "root.txt"

    def test_list_tracked_files_ignores_git_directory(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "file.txt").write_text("content")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")

        files = tracker.list_tracked_files()
        assert len(files) == 1
        assert all(".git" not in str(f) for f in files)


class TestVersionTrackerRepoSize:
    """Test repository size calculation."""

    def test_get_repository_size_no_git_dir(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        assert tracker.get_repository_size_bytes() == 0

    def test_get_repository_size_with_git_dir(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main")
        (git_dir / "config").write_text("[core]\n")

        size = tracker.get_repository_size_bytes()
        assert size > 0


@pytest.mark.skipif(not GIT_AVAILABLE, reason="GitPython not available")
class TestVersionTrackerWithGit:
    """Tests requiring GitPython."""

    def test_init_repository_creates_git_dir(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        result = tracker.init_repository()

        assert result is True
        assert (tmp_path / ".git").exists()

    def test_init_repository_idempotent(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        tracker.init_repository()
        result = tracker.init_repository()

        assert result is True

    def test_initial_commit_with_files(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("content")

        result = tracker.initial_commit()
        assert result is True

    def test_initial_commit_no_tracked_files(self, tmp_path: Path) -> None:
        # Create tracker that excludes all files
        tracker = VersionTracker(tmp_path, include_patterns=["*.nonexistent"])
        tracker.init_repository()

        # Create a file that won't match the include pattern
        (tmp_path / "test.txt").write_text("content")

        result = tracker.initial_commit()
        assert result is False

    def test_commit_all(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("initial")
        tracker.initial_commit()

        (tmp_path / "test.txt").write_text("modified")
        result = tracker.commit_all("Update test.txt")

        assert result is True

    def test_commit_all_no_changes(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("content")
        tracker.initial_commit()

        result = tracker.commit_all("No changes")
        assert result is False

    def test_commit_files(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        tracker.initial_commit()

        (tmp_path / "a.txt").write_text("a modified")
        result = tracker.commit_files(["a.txt"], "Update a.txt")

        assert result is True

    def test_get_file_history(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("v1")
        tracker.initial_commit("First commit")

        (tmp_path / "test.txt").write_text("v2")
        tracker.commit_all("Second commit")

        history = tracker.get_file_history("test.txt")
        assert len(history) >= 2
        assert all(isinstance(e, VersionEntry) for e in history)

    def test_get_recent_changes(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("content")
        tracker.initial_commit("Initial")

        changes = tracker.get_recent_changes()
        assert len(changes) >= 1
        assert all(isinstance(c, ChangeEntry) for c in changes)

    def test_diff_versions(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("line1\n")
        tracker.initial_commit("v1")

        (tmp_path / "test.txt").write_text("line1\nline2\n")
        tracker.commit_all("v2")

        history = tracker.get_file_history("test.txt")
        if len(history) >= 2:
            diff = tracker.diff_versions("test.txt", history[1].commit_hash, history[0].commit_hash)
            assert isinstance(diff, str)

    def test_restore_file(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("original")
        tracker.initial_commit("Original")

        (tmp_path / "test.txt").write_text("modified")
        tracker.commit_all("Modified")

        history = tracker.get_file_history("test.txt")
        if len(history) >= 2:
            result = tracker.restore_file("test.txt", history[1].commit_hash)
            assert result is True
            assert (tmp_path / "test.txt").read_text() == "original"

    def test_optimize_repository(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        (tmp_path / "test.txt").write_text("content")
        tracker.initial_commit()

        result = tracker.optimize_repository()
        assert result is True


class TestVersionTrackerWithoutGit:
    """Tests when GitPython is mocked as unavailable."""

    def test_get_repo_returns_none_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, 'is_available', return_value=False):
            assert tracker._get_repo() is None

    def test_init_repository_returns_false_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, 'is_available', return_value=False):
            assert tracker.init_repository() is False

    def test_commit_all_returns_false_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, '_get_repo', return_value=None):
            assert tracker.commit_all("message") is False

    def test_get_file_history_returns_empty_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, '_get_repo', return_value=None):
            assert tracker.get_file_history("file.txt") == []

    def test_get_recent_changes_returns_empty_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, '_get_repo', return_value=None):
            assert tracker.get_recent_changes() == []

    def test_diff_versions_returns_empty_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, '_get_repo', return_value=None):
            assert tracker.diff_versions("file.txt", "abc", "def") == ""

    def test_restore_file_returns_false_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, '_get_repo', return_value=None):
            assert tracker.restore_file("file.txt", "abc") is False

    def test_optimize_repository_returns_false_when_unavailable(self, tmp_path: Path) -> None:
        tracker = VersionTracker(tmp_path)
        with patch.object(tracker, '_get_repo', return_value=None):
            assert tracker.optimize_repository() is False


class TestVersionEntry:
    """Test VersionEntry dataclass."""

    def test_version_entry_creation(self) -> None:
        entry = VersionEntry(
            commit_hash="abc123",
            committed_at=datetime.now(),
            author="Test Author",
            message="Test message",
            file_path="test.txt",
        )
        assert entry.commit_hash == "abc123"
        assert entry.file_path == "test.txt"
        assert entry.size_bytes is None
        assert entry.insertions is None
        assert entry.deletions is None


class TestChangeEntry:
    """Test ChangeEntry dataclass."""

    def test_change_entry_creation(self) -> None:
        entry = ChangeEntry(
            commit_hash="def456",
            committed_at=datetime.now(),
            author="Test Author",
            message="Change message",
            file_path="changed.txt",
        )
        assert entry.commit_hash == "def456"
        assert entry.file_path == "changed.txt"
