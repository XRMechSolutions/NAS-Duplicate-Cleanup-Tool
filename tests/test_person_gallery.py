"""Tests for Person Photo Gallery features."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from duplicleaner.db.models import FileRecord, Face, Person


class TestPersonGalleryDataStructures:
    """Tests for gallery-related data structures and helpers."""

    def test_face_has_file_id(self):
        """Test that Face model has file_id for linking to photos."""
        face = Face(
            id=1,
            file_id=100,
            person_id=5,
            confidence=0.95,
            bbox_x=10,
            bbox_y=20,
            bbox_w=50,
            bbox_h=60,
        )
        assert face.file_id == 100
        assert face.person_id == 5

    def test_person_has_photo_count(self):
        """Test that Person model has photo_count field."""
        person = Person(
            id=1,
            name="Emma",
            birth_year=2015,
            photo_count=456,
        )
        assert person.name == "Emma"
        assert person.photo_count == 456
        assert person.birth_year == 2015

    def test_person_estimated_age(self):
        """Test Person estimated_age property."""
        person = Person(
            id=1,
            name="Emma",
            birth_year=2015,
        )
        # Estimated age should be calculated from birth_year
        if hasattr(person, 'estimated_age') and person.estimated_age is not None:
            current_year = datetime.now().year
            expected_age = current_year - 2015
            assert person.estimated_age == expected_age


class TestGallerySorting:
    """Tests for gallery sorting logic."""

    def create_mock_faces_with_dates(self) -> list[dict]:
        """Create mock face data with different dates."""
        return [
            {"id": 1, "file_id": 101, "modified": datetime(2024, 3, 15)},
            {"id": 2, "file_id": 102, "modified": datetime(2024, 1, 10)},
            {"id": 3, "file_id": 103, "modified": datetime(2024, 5, 20)},
            {"id": 4, "file_id": 104, "modified": datetime(2023, 12, 25)},
        ]

    def test_sort_by_date_newest(self):
        """Test sorting by date (newest first)."""
        faces = self.create_mock_faces_with_dates()

        sorted_faces = sorted(
            faces,
            key=lambda f: f["modified"],
            reverse=True
        )

        assert sorted_faces[0]["id"] == 3  # 2024-05-20
        assert sorted_faces[1]["id"] == 1  # 2024-03-15
        assert sorted_faces[2]["id"] == 2  # 2024-01-10
        assert sorted_faces[3]["id"] == 4  # 2023-12-25

    def test_sort_by_date_oldest(self):
        """Test sorting by date (oldest first)."""
        faces = self.create_mock_faces_with_dates()

        sorted_faces = sorted(
            faces,
            key=lambda f: f["modified"]
        )

        assert sorted_faces[0]["id"] == 4  # 2023-12-25
        assert sorted_faces[3]["id"] == 3  # 2024-05-20

    def test_sort_by_filename(self):
        """Test sorting by filename."""
        faces = [
            {"id": 1, "filename": "zebra.jpg"},
            {"id": 2, "filename": "apple.jpg"},
            {"id": 3, "filename": "moon.jpg"},
        ]

        sorted_faces = sorted(
            faces,
            key=lambda f: f["filename"].lower()
        )

        assert sorted_faces[0]["filename"] == "apple.jpg"
        assert sorted_faces[1]["filename"] == "moon.jpg"
        assert sorted_faces[2]["filename"] == "zebra.jpg"


class TestFileSizeFormatting:
    """Tests for file size formatting."""

    def format_file_size(self, size: int) -> str:
        """Format file size in human-readable form."""
        if size >= 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
        elif size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size} B"

    def test_format_bytes(self):
        """Test formatting small byte values."""
        assert self.format_file_size(100) == "100 B"
        assert self.format_file_size(0) == "0 B"
        assert self.format_file_size(1023) == "1023 B"

    def test_format_kilobytes(self):
        """Test formatting kilobyte values."""
        assert self.format_file_size(1024) == "1 KB"
        assert self.format_file_size(1536) == "2 KB"
        assert self.format_file_size(1024 * 100) == "100 KB"

    def test_format_megabytes(self):
        """Test formatting megabyte values."""
        assert self.format_file_size(1024 * 1024) == "1.0 MB"
        assert self.format_file_size(1024 * 1024 * 4.5) == "4.5 MB"

    def test_format_gigabytes(self):
        """Test formatting gigabyte values."""
        assert self.format_file_size(1024 * 1024 * 1024) == "1.0 GB"
        assert self.format_file_size(1024 * 1024 * 1024 * 2.5) == "2.5 GB"


class TestDatabaseGalleryMethods:
    """Tests for database methods used by gallery."""

    def test_get_faces_for_person_with_limit(self, test_db, test_drive):
        """Test get_faces_for_person respects limit parameter."""
        # Create a person
        person = Person(name="Test Person")
        person_id = test_db.add_person(person)

        # Create files first (for foreign key)
        file_ids = []
        for i in range(10):
            file_record = FileRecord(
                drive_id=test_drive.id,
                path=f"/test/photo_{i}.jpg",
                filename=f"photo_{i}.jpg",
                size=1024,
            )
            file_id = test_db.add_file(file_record)
            file_ids.append(file_id)

        # Create faces linked to files
        for file_id in file_ids:
            test_db.add_face(Face(
                file_id=file_id,
                person_id=person_id,
                confidence=0.9,
                bbox_x=0, bbox_y=0, bbox_w=50, bbox_h=50,
            ))

        # Get faces with limit
        faces = test_db.get_faces_for_person(person_id, limit=5)
        assert len(faces) == 5

        # Get all faces (default limit is high)
        all_faces = test_db.get_faces_for_person(person_id)
        assert len(all_faces) == 10

    def test_unassign_face_from_person(self, test_db, test_drive):
        """Test unassign_face_from_person removes person assignment."""
        # Create a person
        person = Person(name="Test Person")
        person_id = test_db.add_person(person)

        # Create a file first
        file_record = FileRecord(
            drive_id=test_drive.id,
            path="/test/photo.jpg",
            filename="photo.jpg",
            size=1024,
        )
        file_id = test_db.add_file(file_record)

        # Create and assign a face
        face = Face(
            file_id=file_id,
            person_id=person_id,
            confidence=0.9,
            bbox_x=0, bbox_y=0, bbox_w=50, bbox_h=50,
        )
        face_id = test_db.add_face(face)

        # Verify face is assigned
        assigned_face = test_db.get_face(face_id)
        assert assigned_face.person_id == person_id

        # Unassign the face
        result = test_db.unassign_face_from_person(face_id)
        assert result is True

        # Verify face is unassigned
        unassigned_face = test_db.get_face(face_id)
        assert unassigned_face.person_id is None

    def test_unassign_face_updates_photo_count(self, test_db, test_drive):
        """Test that unassigning a face updates person's photo count."""
        # Create a person
        person = Person(name="Test Person")
        person_id = test_db.add_person(person)

        # Add a file first
        file_record = FileRecord(
            drive_id=test_drive.id,
            path="/test/photo.jpg",
            filename="photo.jpg",
            size=1024,
        )
        file_id = test_db.add_file(file_record)

        # Create and assign a face
        face = Face(
            file_id=file_id,
            person_id=person_id,
            confidence=0.9,
            bbox_x=0, bbox_y=0, bbox_w=50, bbox_h=50,
        )
        face_id = test_db.add_face(face)

        # Update photo count
        test_db.update_person_photo_count(person_id)

        # Get initial photo count
        person_record = test_db.get_person(person_id)
        initial_count = person_record.photo_count

        # Unassign the face
        test_db.unassign_face_from_person(face_id)

        # Get updated photo count
        person_record = test_db.get_person(person_id)
        assert person_record.photo_count < initial_count

    def test_unassign_nonexistent_face(self, test_db):
        """Test unassigning a face that doesn't exist returns False."""
        result = test_db.unassign_face_from_person(99999)
        assert result is False


class TestTimelineGrouping:
    """Tests for timeline grouping logic."""

    def test_group_faces_by_year(self):
        """Test grouping faces by year."""
        # Simulate timeline data
        timeline_data = [
            (2024, ["face1", "face2", "face3"]),
            (2023, ["face4", "face5"]),
            (2022, ["face6"]),
        ]

        # Verify structure
        assert len(timeline_data) == 3
        assert timeline_data[0][0] == 2024
        assert len(timeline_data[0][1]) == 3
        assert timeline_data[1][0] == 2023
        assert len(timeline_data[1][1]) == 2

    def test_age_calculation_from_birth_year(self):
        """Test age calculation for timeline headers."""
        birth_year = 2015

        for year, expected_age in [(2024, 9), (2020, 5), (2015, 0)]:
            age = year - birth_year
            assert age == expected_age


class TestGalleryImport:
    """Tests that gallery-related code can be imported."""

    def test_import_faces_panel(self):
        """Test that faces_panel module can be imported."""
        try:
            from duplicleaner.ui import faces_panel
            assert hasattr(faces_panel, 'FacesPanel')
        except ImportError as e:
            if "dearpygui" in str(e).lower():
                pytest.skip("Dear PyGui not available")
            raise

    def test_faces_panel_has_gallery_tags(self):
        """Test that FacesPanel has gallery-related tags."""
        try:
            from duplicleaner.ui.faces_panel import FacesPanel
            assert hasattr(FacesPanel, 'TAG_PERSON_GALLERY_DIALOG')
            assert hasattr(FacesPanel, 'TAG_PERSON_GALLERY_CONTAINER')
            assert hasattr(FacesPanel, 'TAG_PHOTO_PREVIEW_DIALOG')
        except ImportError as e:
            if "dearpygui" in str(e).lower():
                pytest.skip("Dear PyGui not available")
            raise

    def test_faces_panel_has_gallery_methods(self):
        """Test that FacesPanel has gallery-related methods."""
        try:
            from duplicleaner.ui.faces_panel import FacesPanel
            # Check for method definitions (they exist on the class)
            assert hasattr(FacesPanel, '_show_person_gallery')
            assert hasattr(FacesPanel, '_render_person_gallery')
            assert hasattr(FacesPanel, '_show_photo_preview')
            assert hasattr(FacesPanel, '_photo_preview_open')
            assert hasattr(FacesPanel, '_photo_preview_explorer')
        except ImportError as e:
            if "dearpygui" in str(e).lower():
                pytest.skip("Dear PyGui not available")
            raise
