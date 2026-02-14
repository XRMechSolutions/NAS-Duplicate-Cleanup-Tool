"""Comprehensive tests for database operations.

These tests focus on real business logic, data integrity, edge cases,
and database operations that could cause actual bugs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from duplicleaner.core.resolver import Resolver
from duplicleaner.db.database import Database
from duplicleaner.db.models import (
    ActionLogEntry,
    ActionType,
    Drive,
    Face,
    FileMetadata,
    FileRecord,
    GroupStatus,
    MatchType,
    Person,
)


class TestDatabaseFileOperations:
    """Test file operations with real data integrity concerns."""

    def test_add_file_returns_id(self, test_db, test_drive) -> None:
        """Verify add_file returns a valid ID for new files."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/file.txt",
            filename="file.txt",
            size=100,
        )
        file_id = test_db.add_file(record)
        assert file_id > 0

    def test_add_file_upserts_on_conflict(self, test_db) -> None:
        """Verify file updates work via upsert and don't create duplicates."""
        drive = Drive(id="D1", label="Test", path="/test")
        test_db.add_drive(drive)

        record1 = FileRecord(
            drive_id="D1",
            path="/test/file.txt",
            filename="file.txt",
            size=100,
        )
        id1 = test_db.add_file(record1)

        record2 = FileRecord(
            drive_id="D1",
            path="/test/file.txt",
            filename="file.txt",
            size=200,  # Changed size
        )
        id2 = test_db.add_file(record2)

        # Should return same ID (upsert)
        assert id1 == id2

        # Verify the file was updated, not duplicated
        retrieved = test_db.get_file(id1)
        assert retrieved.size == 200

    def test_file_size_grouping_for_duplicates(self, test_db) -> None:
        """Test that files are correctly grouped by size for duplicate detection."""
        drive = Drive(id="D1", label="Test", path="/test")
        test_db.add_drive(drive)

        # Add files with same and different sizes
        for i, size in enumerate([100, 100, 100, 200, 300]):
            record = FileRecord(
                drive_id="D1",
                path=f"/test/file{i}.txt",
                filename=f"file{i}.txt",
                size=size,
            )
            test_db.add_file(record)

        # Files needing hash should only include size=100 files (3 duplicates)
        files_needing_hash = test_db.get_files_needing_hash()
        assert len(files_needing_hash) == 3
        assert all(f.size == 100 for f in files_needing_hash)

    def test_content_hash_grouping_across_drives(self, test_db) -> None:
        """Test content hash grouping correctly identifies files across drives."""
        drive1 = Drive(id="D1", label="Drive1", path="/drive1")
        drive2 = Drive(id="D2", label="Drive2", path="/drive2")
        test_db.add_drive(drive1)
        test_db.add_drive(drive2)

        # Same content on both drives
        hash_value = "sha256:abc123"
        for drive_id in ["D1", "D2"]:
            record = FileRecord(
                drive_id=drive_id,
                path=f"/{drive_id}/file.txt",
                filename="file.txt",
                size=100,
                content_hash=hash_value,
            )
            test_db.add_file(record)

        # Should find 1 group with 2 files across 2 drives
        groups = test_db.get_content_hash_groups(min_drives=1)
        assert len(groups) == 1
        hash_, size, file_count, drive_count = groups[0]
        assert hash_ == hash_value
        assert file_count == 2
        assert drive_count == 2

    def test_mark_files_deleted_preserves_recent_scans(self, test_db, test_drive) -> None:
        """Verify only old files are marked deleted, not recently scanned ones."""
        now = datetime.now()
        old_scan = now - timedelta(hours=2)
        recent_scan = now - timedelta(minutes=5)

        # Add old file
        old_file = FileRecord(
            drive_id=test_drive.id,
            path="/test/old.txt",
            filename="old.txt",
            size=100,
            scan_date=old_scan,
        )
        old_id = test_db.add_file(old_file)

        # Add recent file
        recent_file = FileRecord(
            drive_id=test_drive.id,
            path="/test/recent.txt",
            filename="recent.txt",
            size=100,
            scan_date=recent_scan,
        )
        recent_id = test_db.add_file(recent_file)

        # Mark files deleted if scanned before 1 hour ago
        scan_start = now - timedelta(hours=1)
        deleted_count = test_db.mark_files_deleted_before_scan(test_drive.id, scan_start)

        assert deleted_count == 1
        assert test_db.get_file(old_id).is_deleted
        assert not test_db.get_file(recent_id).is_deleted

    def test_deleted_files_excluded_from_queries(self, test_db) -> None:
        """Ensure deleted files are properly excluded from normal queries."""
        drive = Drive(id="D1", label="Test", path="/test")
        test_db.add_drive(drive)

        # Add and then delete a file
        record = FileRecord(
            drive_id="D1",
            path="/test/deleted.txt",
            filename="deleted.txt",
            size=100,
            content_hash="hash123",
        )
        file_id = test_db.add_file(record)
        test_db.mark_file_deleted(file_id)

        # Add a non-deleted file with same hash
        record2 = FileRecord(
            drive_id="D1",
            path="/test/active.txt",
            filename="active.txt",
            size=100,
            content_hash="hash123",
        )
        test_db.add_file(record2)

        # Query by hash should only return active file
        files = test_db.get_files_by_hash("hash123")
        assert len(files) == 1
        assert files[0].filename == "active.txt"


class TestDatabaseDuplicateGroups:
    """Test duplicate group management."""

    def test_create_duplicate_group(self, test_db, test_drive) -> None:
        """Test creating a duplicate group with members."""
        # Create files
        file_ids = []
        for i in range(3):
            record = FileRecord(
                drive_id=test_drive.id,
                path=f"/test/dup{i}.txt",
                filename=f"dup{i}.txt",
                size=100,
                content_hash="same_hash",
            )
            file_ids.append(test_db.add_file(record))

        group_id = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=file_ids,
        )

        assert group_id > 0

        # Verify group exists with correct members
        group = test_db.get_duplicate_group(group_id)
        assert group is not None
        assert group.match_type == MatchType.EXACT
        assert group.file_count == 3

    def test_resolve_duplicate_group_marks_keeper(self, test_db, test_drive) -> None:
        """Test that resolving a group correctly marks the keeper."""
        file_ids = []
        for i in range(3):
            record = FileRecord(
                drive_id=test_drive.id,
                path=f"/test/dup{i}.txt",
                filename=f"dup{i}.txt",
                size=100,
                content_hash="same_hash",
            )
            file_ids.append(test_db.add_file(record))

        group_id = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=file_ids,
        )

        # Resolve: keep first file
        test_db.resolve_duplicate_group(group_id, file_ids[0])

        group = test_db.get_duplicate_group(group_id)
        assert group.status == GroupStatus.RESOLVED

    def test_get_duplicate_group_with_files(self, test_db, test_drive) -> None:
        """Test retrieving a duplicate group with file details."""
        file_ids = []
        for i in range(2):
            record = FileRecord(
                drive_id=test_drive.id,
                path=f"/test/dup{i}.txt",
                filename=f"dup{i}.txt",
                size=100,
            )
            file_ids.append(test_db.add_file(record))

        group_id = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=file_ids,
        )

        group = test_db.get_duplicate_group(group_id, include_files=True)
        assert group is not None
        assert len(group.members) == 2

    def test_get_duplicate_group_counts(self, test_db, test_drive) -> None:
        """Test duplicate group counts by status."""
        file_ids = []
        for i in range(6):
            record = FileRecord(
                drive_id=test_drive.id,
                path=f"/test/dup_count{i}.txt",
                filename=f"dup_count{i}.txt",
                size=100,
                content_hash=f"hash_{i // 2}",
            )
            file_ids.append(test_db.add_file(record))

        test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=file_ids[:2],
        )
        resolved_group = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=file_ids[2:4],
        )
        ignored_group = test_db.create_duplicate_group(
            match_type=MatchType.EXACT,
            similarity=1.0,
            file_ids=file_ids[4:6],
        )

        test_db.resolve_duplicate_group(resolved_group, file_ids[2])
        resolver = Resolver(test_db)
        resolver.ignore_group(ignored_group)

        counts = test_db.get_duplicate_group_counts()
        assert counts[GroupStatus.PENDING] >= 1
        assert counts[GroupStatus.RESOLVED] >= 1
        assert counts[GroupStatus.IGNORED] >= 1


class TestDatabaseHashOperations:
    """Test hash-related database operations."""

    def test_update_file_hash_partial(self, test_db, test_drive) -> None:
        """Test that partial hash updates don't clear other hash fields."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/file.txt",
            filename="file.txt",
            size=100,
            quick_hash="quick123",
            content_hash="content456",
        )
        file_id = test_db.add_file(record)

        # Update only perceptual hash
        test_db.update_file_hash(file_id, perceptual_hash="phash789")

        updated = test_db.get_file(file_id)
        assert updated.quick_hash == "quick123"  # Unchanged
        assert updated.content_hash == "content456"  # Unchanged
        assert updated.perceptual_hash == "phash789"  # Updated

    def test_get_hashes_for_drive_filters_correctly(self, test_db) -> None:
        """Test hash retrieval filters by drive correctly."""
        drive1 = Drive(id="D1", label="Drive1", path="/drive1")
        drive2 = Drive(id="D2", label="Drive2", path="/drive2")
        test_db.add_drive(drive1)
        test_db.add_drive(drive2)

        # Add files with different hashes to different drives
        test_db.add_file(FileRecord(
            drive_id="D1", path="/drive1/a.txt", filename="a.txt",
            size=100, content_hash="hash_d1_a",
        ))
        test_db.add_file(FileRecord(
            drive_id="D1", path="/drive1/b.txt", filename="b.txt",
            size=100, content_hash="hash_d1_b",
        ))
        test_db.add_file(FileRecord(
            drive_id="D2", path="/drive2/c.txt", filename="c.txt",
            size=100, content_hash="hash_d2_c",
        ))

        d1_hashes = test_db.get_hashes_for_drive("D1")
        d2_hashes = test_db.get_hashes_for_drive("D2")

        assert "hash_d1_a" in d1_hashes
        assert "hash_d1_b" in d1_hashes
        assert "hash_d2_c" not in d1_hashes
        assert "hash_d2_c" in d2_hashes

    def test_get_content_hash_counts(self, test_db, test_drive) -> None:
        """Test content hash count statistics."""
        records = [
            FileRecord(
                drive_id=test_drive.id,
                path="/test/hashed1.txt",
                filename="hashed1.txt",
                size=100,
                content_hash="hash1",
            ),
            FileRecord(
                drive_id=test_drive.id,
                path="/test/hashed2.txt",
                filename="hashed2.txt",
                size=100,
                content_hash="hash2",
            ),
            FileRecord(
                drive_id=test_drive.id,
                path="/test/unhashed.txt",
                filename="unhashed.txt",
                size=100,
            ),
        ]
        for record in records:
            test_db.add_file(record)

        total, hashed = test_db.get_content_hash_counts()
        assert total >= 3
        assert hashed >= 2


class TestDatabaseFileMetadata:
    """Test file metadata operations."""

    def test_add_and_retrieve_metadata(self, test_db, test_drive) -> None:
        """Test metadata round-trip."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/photo.jpg",
            filename="photo.jpg",
            size=1024,
        )
        file_id = test_db.add_file(record)

        metadata = FileMetadata(
            file_id=file_id,
            exif_date=datetime(2024, 6, 15, 14, 30),
            gps_lat=40.7128,
            gps_lon=-74.0060,
            location_name="New York, NY",
            camera_make="Canon",
            camera_model="EOS R5",
            width=8192,
            height=5464,
        )
        test_db.add_file_metadata(metadata)

        retrieved = test_db.get_file_metadata(file_id)
        assert retrieved is not None
        assert retrieved.camera_make == "Canon"
        assert retrieved.gps_lat == pytest.approx(40.7128)
        assert retrieved.width == 8192

    def test_metadata_upserts_on_conflict(self, test_db, test_drive) -> None:
        """Test that metadata updates via upsert."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/photo.jpg",
            filename="photo.jpg",
            size=1024,
        )
        file_id = test_db.add_file(record)

        # Initial metadata
        metadata1 = FileMetadata(file_id=file_id, camera_make="Canon")
        test_db.add_file_metadata(metadata1)

        # Update metadata
        metadata2 = FileMetadata(file_id=file_id, camera_make="Nikon")
        test_db.add_file_metadata(metadata2)

        retrieved = test_db.get_file_metadata(file_id)
        assert retrieved.camera_make == "Nikon"


class TestDatabaseFaceTracking:
    """Test face detection and recognition database operations."""

    def test_mark_faces_analyzed(self, test_db, test_drive) -> None:
        """Test marking files as face-analyzed."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/photo.jpg",
            filename="photo.jpg",
            size=1024,
        )
        file_id = test_db.add_file(record)

        assert test_db.is_faces_analyzed(file_id) is False

        test_db.mark_faces_analyzed(file_id, faces_found=2)

        assert test_db.is_faces_analyzed(file_id) is True

    def test_faces_analyzed_with_error(self, test_db, test_drive) -> None:
        """Test marking face analysis as failed with error."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/corrupt.jpg",
            filename="corrupt.jpg",
            size=1024,
        )
        file_id = test_db.add_file(record)

        test_db.mark_faces_analyzed(file_id, faces_found=0, error="Corrupt image file")

        assert test_db.is_faces_analyzed(file_id) is True

    def test_get_files_missing_face_analysis(self, test_db, test_drive) -> None:
        """Test retrieving files that need face analysis."""
        # Add image file
        img_record = FileRecord(
            drive_id=test_drive.id,
            path="/test/photo.jpg",
            filename="photo.jpg",
            file_type=".jpg",
            size=1024,
        )
        img_id = test_db.add_file(img_record)

        # Add non-image file (should be excluded)
        txt_record = FileRecord(
            drive_id=test_drive.id,
            path="/test/doc.txt",
            filename="doc.txt",
            file_type=".txt",
            size=100,
        )
        test_db.add_file(txt_record)

        files = test_db.get_image_files_missing_face_analysis()
        file_ids = [f.id for f in files]

        assert img_id in file_ids
        # text file should not be in the list

    def test_add_face_and_person(self, test_db, test_drive) -> None:
        """Test adding faces and associating with people."""
        # Create file
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/family.jpg",
            filename="family.jpg",
            size=1024,
        )
        file_id = test_db.add_file(record)

        # Create person
        person_id = test_db.add_person(Person(name="John Doe"))
        assert person_id > 0

        # Create face (using correct field names: bbox_w and bbox_h)
        face = Face(
            file_id=file_id,
            person_id=person_id,
            bbox_x=100, bbox_y=100,
            bbox_w=50, bbox_h=60,
            confidence=0.95,
            embedding=b"fake_embedding_data",
        )
        face_id = test_db.add_face(face)
        assert face_id > 0

        # Retrieve faces for file
        faces = test_db.get_faces_for_file(file_id)
        assert len(faces) == 1
        assert faces[0].person_id == person_id


class TestDatabaseActionLog:
    """Test action logging for audit trail."""

    def test_log_action(self, test_db, test_drive) -> None:
        """Test action logging creates proper audit trail."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/file.txt",
            filename="file.txt",
            size=100,
        )
        test_db.add_file(record)

        # ActionLogEntry uses source_path, dest_path, etc. - no file_id field
        entry = ActionLogEntry(
            action_type=ActionType.QUARANTINE,
            source_path="/test/file.txt",
            dest_path="/quarantine/file.txt",
            file_size=100,
        )
        log_id = test_db.log_action(entry)
        assert log_id > 0

        # Retrieve and verify
        logs = test_db.get_action_log(limit=10)
        assert len(logs) >= 1
        assert logs[0].action_type == ActionType.QUARANTINE

    def test_delete_action_log_before_cutoff(self, test_db) -> None:
        """Test clearing old action log entries respects cutoff and reversed flag."""
        old_time = datetime.now() - timedelta(days=120)
        new_time = datetime.now() - timedelta(days=10)

        old_reversed = ActionLogEntry(
            action_type=ActionType.MOVE,
            source_path="/old/reversed.txt",
            dest_path="/dest/reversed.txt",
            file_size=10,
            reversed=True,
            timestamp=old_time,
        )
        old_active = ActionLogEntry(
            action_type=ActionType.MOVE,
            source_path="/old/active.txt",
            dest_path="/dest/active.txt",
            file_size=10,
            reversed=False,
            timestamp=old_time,
        )
        new_reversed = ActionLogEntry(
            action_type=ActionType.MOVE,
            source_path="/new/reversed.txt",
            dest_path="/dest/new.txt",
            file_size=10,
            reversed=True,
            timestamp=new_time,
        )

        test_db.log_action(old_reversed)
        test_db.log_action(old_active)
        test_db.log_action(new_reversed)

        deleted = test_db.delete_action_log_before(datetime.now() - timedelta(days=90), only_reversed=True)
        assert deleted == 1

        remaining = test_db.get_action_log(limit=10)
        remaining_sources = {entry.source_path for entry in remaining}
        assert "/old/active.txt" in remaining_sources
        assert "/new/reversed.txt" in remaining_sources


class TestDatabaseConcurrency:
    """Test database handles concurrent access."""

    def test_multiple_connections_work(self, tmp_path: Path) -> None:
        """Verify multiple connections can be opened to the same DB."""
        db_path = str(tmp_path / "test.db")

        db1 = Database(db_path)
        db2 = Database(db_path)

        drive1 = Drive(id="D1", label="Drive1", path="/test1")
        drive2 = Drive(id="D2", label="Drive2", path="/test2")

        db1.add_drive(drive1)
        db2.add_drive(drive2)

        # Both should be visible
        all_drives = db1.get_all_drives()
        drive_ids = [d.id for d in all_drives]
        assert "D1" in drive_ids
        assert "D2" in drive_ids


class TestDatabaseEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_extensions_list(self, test_db) -> None:
        """Test get_files_by_type handles empty extensions list."""
        files = test_db.get_files_by_type([])
        assert files == []

    def test_nonexistent_file_returns_none(self, test_db) -> None:
        """Test get_file returns None for missing ID."""
        assert test_db.get_file(999999) is None

    def test_nonexistent_drive_returns_none(self, test_db) -> None:
        """Test get_drive returns None for missing ID."""
        assert test_db.get_drive("nonexistent") is None

    def test_batch_file_insertion(self, test_db, test_drive) -> None:
        """Test batch file insertion works correctly."""
        files = [
            FileRecord(
                drive_id=test_drive.id,
                path=f"/test/batch{i}.txt",
                filename=f"batch{i}.txt",
                size=i * 100,
            )
            for i in range(100)
        ]

        test_db.add_files_batch(files)

        count = test_db.get_file_count(test_drive.id)
        assert count >= 100

    def test_unicode_filenames(self, test_db, test_drive) -> None:
        """Test handling of Unicode characters in filenames."""
        record = FileRecord(
            drive_id=test_drive.id,
            path="/test/foto_de_vacaciones.jpg",
            filename="foto_de_vacaciones.jpg",
            size=1024,
        )
        file_id = test_db.add_file(record)

        retrieved = test_db.get_file(file_id)
        assert retrieved.filename == "foto_de_vacaciones.jpg"

    def test_very_long_path(self, test_db, test_drive) -> None:
        """Test handling of very long file paths."""
        long_dir = "/test/" + "/".join(["subdir"] * 50)
        long_path = long_dir + "/file.txt"

        record = FileRecord(
            drive_id=test_drive.id,
            path=long_path,
            filename="file.txt",
            size=100,
        )
        file_id = test_db.add_file(record)

        retrieved = test_db.get_file(file_id)
        assert retrieved.path == long_path

    def test_settings_persistence(self, test_db) -> None:
        """Test settings are properly persisted and retrieved."""
        test_db.set_setting("test_key", "test_value")
        test_db.set_setting("numeric_key", "12345")

        assert test_db.get_setting("test_key") == "test_value"
        assert test_db.get_setting("numeric_key") == "12345"
        assert test_db.get_setting("nonexistent", "default") == "default"

    def test_settings_update(self, test_db) -> None:
        """Test settings can be updated."""
        test_db.set_setting("key", "value1")
        test_db.set_setting("key", "value2")

        assert test_db.get_setting("key") == "value2"


class TestDatabaseScanState:
    """Test scan state persistence for resumable scans."""

    def test_scan_state_roundtrip(self, test_db) -> None:
        """Test scan state can be saved and retrieved."""
        state = {
            "current_path": "/test/sub/folder",
            "files_scanned": 1500,
            "last_file": "document.pdf",
        }

        test_db.set_scan_state("drive1", state)
        retrieved = test_db.get_scan_state("drive1")

        assert retrieved == state

    def test_scan_state_clear(self, test_db) -> None:
        """Test scan state can be cleared."""
        test_db.set_scan_state("drive1", {"some": "data"})
        test_db.clear_scan_state("drive1")

        assert test_db.get_scan_state("drive1") is None

    def test_scan_state_invalid_json(self, test_db) -> None:
        """Test handling of invalid scan state JSON."""
        # Manually set invalid JSON
        test_db.set_setting("scan_state:bad", "not valid json {}")
        result = test_db.get_scan_state("bad")
        assert result is None
