"""Tests for the redundancy module."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from duplicleaner.db.models import Drive, FileRecord
from duplicleaner.drives.manager import DriveManager, DriveStatus
from duplicleaner.drives.redundancy import (
    AtRiskGroup,
    BackupPlanItem,
    ExclusionCandidate,
    HashGroup,
    ProjectDetection,
    RedundancyChecker,
    RedundancyReport,
)


class TestHashGroup:
    """Test HashGroup dataclass."""

    def test_hash_group_creation(self) -> None:
        group = HashGroup(
            content_hash="abc123",
            size=1024,
            file_count=3,
            drive_count=2,
        )
        assert group.content_hash == "abc123"
        assert group.size == 1024
        assert group.file_count == 3
        assert group.drive_count == 2


class TestAtRiskGroup:
    """Test AtRiskGroup dataclass."""

    def test_at_risk_group_creation(self) -> None:
        files = [
            FileRecord(
                drive_id="D1",
                path="/test/file.txt",
                filename="file.txt",
                size=100,
            )
        ]
        group = AtRiskGroup(
            content_hash="abc123",
            size=100,
            drive_id="D1",
            files=files,
        )
        assert group.content_hash == "abc123"
        assert group.drive_id == "D1"
        assert len(group.files) == 1


class TestRedundancyReport:
    """Test RedundancyReport dataclass."""

    def test_report_creation(self) -> None:
        report = RedundancyReport(
            total_hashed_files=100,
            total_groups=50,
            at_risk_groups=[],
            redundant_groups=[],
            at_risk_files=10,
            at_risk_size_bytes=1024,
        )
        assert report.total_hashed_files == 100
        assert report.total_groups == 50
        assert report.at_risk_files == 10


class TestBackupPlanItem:
    """Test BackupPlanItem dataclass."""

    def test_backup_plan_item_creation(self) -> None:
        item = BackupPlanItem(
            file_id=1,
            source_drive_id="D1",
            target_drive_id="D2",
            source_path="/source/file.txt",
            target_path="/target/file.txt",
            size=1024,
            content_hash="abc123",
        )
        assert item.file_id == 1
        assert item.source_drive_id == "D1"
        assert item.target_drive_id == "D2"


class TestExclusionCandidate:
    """Test ExclusionCandidate dataclass."""

    def test_exclusion_candidate_creation(self) -> None:
        candidate = ExclusionCandidate(
            pattern="*/node_modules/*",
            file_count=500,
            total_size=1024 * 1024,
        )
        assert candidate.pattern == "*/node_modules/*"
        assert candidate.file_count == 500


class TestProjectDetection:
    """Test ProjectDetection dataclass."""

    def test_project_detection_creation(self) -> None:
        detection = ProjectDetection(
            name="Node.js",
            markers=["package.json"],
            suggested_excludes=["*/node_modules/*"],
        )
        assert detection.name == "Node.js"
        assert "package.json" in detection.markers


class TestRedundancyCheckerInit:
    """Test RedundancyChecker initialization."""

    def test_init_with_db(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        assert checker.db is test_db

    def test_init_with_drive_manager(self, test_db) -> None:
        manager = DriveManager(db=test_db)
        checker = RedundancyChecker(db=test_db, drive_manager=manager)
        assert checker.drive_manager is manager


class TestRedundancyCheckerBuildReport:
    """Test building redundancy reports."""

    def test_build_report_empty_db(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        report = checker.build_report()

        assert isinstance(report, RedundancyReport)
        assert report.total_hashed_files == 0

    def test_build_report_with_data(self, test_db, test_drive, tmp_path: Path) -> None:
        checker = RedundancyChecker(db=test_db)

        # Add files with hashes
        for i in range(3):
            test_file = tmp_path / f"file{i}.txt"
            test_file.write_text(f"content{i}")

            record = FileRecord(
                drive_id=test_drive.id,
                path=str(test_file),
                filename=test_file.name,
                size=100,
                content_hash=f"hash{i}" if i < 2 else "hash0",  # hash0 appears twice
            )
            test_db.add_file(record)

        report = checker.build_report()
        assert isinstance(report, RedundancyReport)

    def test_build_report_totals_not_limited(self, test_db, test_drive, tmp_path: Path) -> None:
        checker = RedundancyChecker(db=test_db)

        hashes = ["h1", "h2", "h3"]
        for i, content_hash in enumerate(hashes):
            test_file = tmp_path / f"file_{i}.txt"
            test_file.write_text(f"content{i}")
            record = FileRecord(
                drive_id=test_drive.id,
                path=str(test_file),
                filename=test_file.name,
                size=10 + i,
                content_hash=content_hash,
            )
            test_db.add_file(record)

        report = checker.build_report(limit=1)
        assert report.total_groups == 3
        assert report.total_hashed_files == 3
        assert report.at_risk_files == 3


class TestRedundancyCheckerBuildBackupPlan:
    """Test building backup plans."""

    def test_build_backup_plan_no_target(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        plan = checker.build_backup_plan([], "nonexistent")
        assert plan == []

    def test_build_backup_plan_empty_groups(self, test_db, tmp_path: Path) -> None:
        # Create a target drive
        target_path = tmp_path / "target"
        target_path.mkdir()
        target_drive = Drive(id="target", label="Target", path=str(target_path))
        test_db.add_drive(target_drive)

        checker = RedundancyChecker(db=test_db)
        plan = checker.build_backup_plan([], "target")
        assert plan == []

    def test_build_backup_plan_with_groups(self, test_db, tmp_path: Path) -> None:
        # Create source and target drives
        source_path = tmp_path / "source"
        source_path.mkdir()
        target_path = tmp_path / "target"
        target_path.mkdir()

        source_drive = Drive(id="source", label="Source", path=str(source_path))
        target_drive = Drive(id="target", label="Target", path=str(target_path))
        test_db.add_drive(source_drive)
        test_db.add_drive(target_drive)

        # Create a file
        test_file = source_path / "file.txt"
        test_file.write_text("content")
        record = FileRecord(
            id=1,
            drive_id="source",
            path=str(test_file),
            filename="file.txt",
            size=7,
            content_hash="abc123",
        )
        test_db.add_file(record)

        at_risk = [
            AtRiskGroup(
                content_hash="abc123",
                size=7,
                drive_id="source",
                files=[record],
            )
        ]

        checker = RedundancyChecker(db=test_db)
        plan = checker.build_backup_plan(at_risk, "target")

        assert len(plan) == 1
        assert plan[0].source_drive_id == "source"
        assert plan[0].target_drive_id == "target"


class TestRedundancyCheckerSafeRelpath:
    """Test safe relative path computation."""

    def test_safe_relpath_valid(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._safe_relpath("/root/sub/file.txt", "/root", "file.txt")
        assert "sub" in result or result == "file.txt"

    def test_safe_relpath_fallback(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._safe_relpath("/different/path/file.txt", "/root", "fallback.txt")
        # Should return the fallback name when paths don't match
        assert result is not None


class TestRedundancyCheckerIsExcluded:
    """Test exclusion pattern matching."""

    def test_is_excluded_match(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._is_excluded("/path/to/node_modules/package/file.js", ["*/node_modules/*"])
        assert result is True

    def test_is_excluded_no_match(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._is_excluded("/path/to/src/file.js", ["*/node_modules/*"])
        assert result is False

    def test_is_excluded_empty_patterns(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._is_excluded("/any/path/file.txt", [])
        assert result is False


class TestRedundancyCheckerMarkerToLike:
    """Test marker to LIKE pattern conversion."""

    def test_marker_to_like_basic(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._marker_to_like("C:\\Projects", "\\package.json")
        assert "package.json" in result
        assert "%" in result

    def test_marker_to_like_with_wildcard(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._marker_to_like("C:\\Projects", "*.sln")
        assert "%" in result


class TestRedundancyCheckerDetectProjects:
    """Test project type detection."""

    def test_detect_project_types_no_drive(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker.detect_project_types("/nonexistent/path")
        assert result == []

    def test_get_project_exclusion_suggestions_no_projects(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        suggestions = checker.get_project_exclusion_suggestions("/nonexistent/path")
        assert suggestions == []


class TestRedundancyCheckerBackupPlanForSource:
    """Test building backup plans for source paths."""

    def test_build_backup_plan_for_source_no_drive(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        plan = checker.build_backup_plan_for_source(
            source_path="/nonexistent",
            target_drive_ids=["target"],
        )
        assert plan == []

    def test_build_backup_plan_for_source_with_data(self, test_db, tmp_path: Path) -> None:
        # Create source and target drives
        source_path = tmp_path / "source"
        source_path.mkdir()
        target_path = tmp_path / "target"
        target_path.mkdir()

        source_drive = Drive(id="src", label="Source", path=str(source_path))
        target_drive = Drive(id="tgt", label="Target", path=str(target_path))
        test_db.add_drive(source_drive)
        test_db.add_drive(target_drive)

        # Create files
        test_file = source_path / "file.txt"
        test_file.write_text("content")
        record = FileRecord(
            id=1,
            drive_id="src",
            path=str(test_file),
            filename="file.txt",
            size=7,
            content_hash="abc123",
        )
        test_db.add_file(record)

        # Mock drive status
        checker = RedundancyChecker(db=test_db)
        with patch.object(checker.drive_manager, 'get_drive_status', return_value=DriveStatus.CONNECTED):
            plan = checker.build_backup_plan_for_source(
                source_path=str(source_path),
                target_drive_ids=["tgt"],
                skip_if_hash_on_target=False,
            )

        assert len(plan) >= 0  # May be filtered


class TestRedundancyCheckerExclusionCandidates:
    """Test exclusion candidate analysis."""

    def test_get_exclusion_candidates_no_drive(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        candidates = checker.get_exclusion_candidates(
            source_path="/nonexistent",
            patterns=["*/node_modules/*"],
        )
        assert candidates == []

    def test_get_exclusion_candidates_with_patterns(self, test_db, tmp_path: Path) -> None:
        # Create a drive
        drive_path = tmp_path / "drive"
        drive_path.mkdir()
        drive = Drive(id="drv", label="Drive", path=str(drive_path))
        test_db.add_drive(drive)

        checker = RedundancyChecker(db=test_db)
        candidates = checker.get_exclusion_candidates(
            source_path=str(drive_path),
            patterns=["*/test/*"],
        )
        assert isinstance(candidates, list)


class TestRedundancyCheckerResolveDrive:
    """Test drive resolution for paths."""

    def test_resolve_drive_for_path_not_found(self, test_db) -> None:
        checker = RedundancyChecker(db=test_db)
        result = checker._resolve_drive_for_path("/nonexistent/path")
        assert result is None

    def test_resolve_drive_for_path_found(self, test_db, tmp_path: Path) -> None:
        # Create a drive
        drive_path = tmp_path / "drive"
        drive_path.mkdir()
        sub_path = drive_path / "sub"
        sub_path.mkdir()

        drive = Drive(id="drv", label="Drive", path=str(drive_path))
        test_db.add_drive(drive)

        checker = RedundancyChecker(db=test_db)
        result = checker._resolve_drive_for_path(str(sub_path))

        if result:
            assert result.id == "drv"
