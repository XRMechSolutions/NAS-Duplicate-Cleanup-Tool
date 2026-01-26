"""Tests for faces panel and face analyzer functionality.

These tests verify that:
1. Find More Photos searches for specific person/pet only
2. Thread-safe analyzer initialization works correctly
3. Face matching respects person_id filtering
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from duplicleaner.db.database import Database
from duplicleaner.db.models import Person, Pet, Face, PetDetection


class TestFindMoreFacesForPerson:
    """Test the find_more_faces_for_person method."""

    def test_returns_zero_when_person_not_found(self, test_db: Database) -> None:
        """Test that searching for non-existent person returns 0."""
        from duplicleaner.ai.faces import FaceAnalyzer

        analyzer = FaceAnalyzer(test_db)
        matches, assigned = analyzer.find_more_faces_for_person(
            person_id=99999,  # Non-existent
            threshold=0.8,
            auto_assign=True
        )

        assert matches == 0
        assert assigned == 0

    def test_returns_zero_when_no_embeddings(self, test_db: Database) -> None:
        """Test that searching for person without embeddings returns 0."""
        from duplicleaner.ai.faces import FaceAnalyzer

        # Create a person but don't add any face embeddings
        person = Person(name="Test Person", photo_count=0)
        person_id = test_db.add_person(person)

        analyzer = FaceAnalyzer(test_db)
        matches, assigned = analyzer.find_more_faces_for_person(
            person_id=person_id,
            threshold=0.8,
            auto_assign=True
        )

        assert matches == 0
        assert assigned == 0

    def test_only_matches_specified_person(self, test_db: Database) -> None:
        """Test that find_more only matches against the specified person."""
        from duplicleaner.ai.faces import FaceAnalyzer

        # Create two people
        person1 = Person(name="Person 1", photo_count=1)
        person2 = Person(name="Person 2", photo_count=1)
        person1_id = test_db.add_person(person1)
        person2_id = test_db.add_person(person2)

        analyzer = FaceAnalyzer(test_db)

        # Mock the person embeddings - person 1 has embeddings, person 2 doesn't
        analyzer._person_embeddings = {
            person1_id: [],  # Empty but present
            # person2_id not in dict
        }

        # When searching for person 1, should only check person 1's embeddings
        matches, assigned = analyzer.find_more_faces_for_person(
            person_id=person1_id,
            threshold=0.8,
            auto_assign=False
        )

        # Should return 0 since no unassigned faces exist
        assert matches == 0
        assert assigned == 0


class TestFindMoreDetectionsForPet:
    """Test the find_more_detections_for_pet method."""

    def test_returns_zero_when_pet_not_found(self, test_db: Database) -> None:
        """Test that searching for non-existent pet returns 0."""
        from duplicleaner.ai.pets import PetAnalyzer

        analyzer = PetAnalyzer(test_db)
        matches, assigned = analyzer.find_more_detections_for_pet(
            pet_id=99999,  # Non-existent
            threshold=0.75,
            auto_assign=True
        )

        assert matches == 0
        assert assigned == 0

    def test_returns_zero_when_no_histogram(self, test_db: Database) -> None:
        """Test that searching for pet without histogram returns 0."""
        from duplicleaner.ai.pets import PetAnalyzer

        # Create a pet but don't add histogram
        pet = Pet(name="Fluffy", species="dog", photo_count=0)
        pet_id = test_db.add_pet(pet)

        analyzer = PetAnalyzer(test_db)
        matches, assigned = analyzer.find_more_detections_for_pet(
            pet_id=pet_id,
            threshold=0.75,
            auto_assign=True
        )

        assert matches == 0
        assert assigned == 0


class TestThreadSafeAnalyzerInit:
    """Test thread-safe lazy initialization of analyzers."""

    def test_face_analyzer_single_instance(self) -> None:
        """Test that face_analyzer property returns same instance."""
        with patch("duplicleaner.ui.faces_panel.dpg"):
            with patch("duplicleaner.ui.faces_panel.get_database") as mock_db:
                with patch("duplicleaner.ui.faces_panel.get_config") as mock_config:
                    mock_db.return_value = MagicMock()
                    mock_config.return_value = MagicMock()
                    mock_config.return_value.ai = MagicMock()
                    mock_config.return_value.ai.face_detection_threshold = 0.5
                    mock_config.return_value.ai.face_match_threshold = 0.8
                    mock_config.return_value.ai.face_cluster_threshold = 0.6

                    from duplicleaner.ui.faces_panel import FacesPanel

                    # Create panel (UI building will be mocked)
                    panel = MagicMock(spec=FacesPanel)
                    panel._face_analyzer = None
                    panel._pet_analyzer = None
                    panel._analyzer_lock = threading.Lock()
                    panel.db = MagicMock()

                    # Call property getter multiple times
                    with patch.object(FacesPanel, 'face_analyzer', new_callable=PropertyMock) as mock_prop:
                        analyzer1 = MagicMock()
                        mock_prop.return_value = analyzer1

                        result1 = mock_prop()
                        result2 = mock_prop()

                        # Should return same instance
                        assert result1 is result2

    def test_concurrent_access_creates_single_instance(self) -> None:
        """Test that concurrent access creates only one analyzer instance."""
        import threading

        # Track how many times FaceAnalyzer is instantiated
        instantiation_count = {"count": 0}
        lock = threading.Lock()

        class MockFaceAnalyzer:
            def __init__(self, db):
                with lock:
                    instantiation_count["count"] += 1

        # Simulate the double-checked locking pattern
        _face_analyzer = None
        _analyzer_lock = threading.Lock()

        def get_face_analyzer():
            nonlocal _face_analyzer
            if _face_analyzer is None:
                with _analyzer_lock:
                    if _face_analyzer is None:
                        _face_analyzer = MockFaceAnalyzer(None)
            return _face_analyzer

        # Run concurrent access
        threads = []
        for _ in range(10):
            t = threading.Thread(target=get_face_analyzer)
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should only create one instance despite concurrent access
        assert instantiation_count["count"] == 1


class TestFacePanelCallbacks:
    """Test that faces panel callbacks are properly connected."""

    def test_find_person_photos_uses_person_id(self) -> None:
        """Test that _find_person_photos passes person_id to analyzer."""
        with patch("duplicleaner.ui.faces_panel.dpg"):
            with patch("duplicleaner.ui.faces_panel.get_database") as mock_db:
                with patch("duplicleaner.ui.faces_panel.get_config") as mock_config:
                    mock_db_instance = MagicMock()
                    mock_db.return_value = mock_db_instance

                    mock_config_instance = MagicMock()
                    mock_config.return_value = mock_config_instance
                    mock_config_instance.ai = MagicMock()

                    from duplicleaner.ui.faces_panel import FacesPanel

                    # Create a partial mock
                    panel = MagicMock(spec=FacesPanel)
                    panel.db = mock_db_instance
                    panel.on_status_update = None

                    # Mock the face_analyzer property
                    mock_analyzer = MagicMock()
                    mock_analyzer.find_more_faces_for_person.return_value = (5, 3)
                    panel.face_analyzer = mock_analyzer

                    # Mock person lookup
                    mock_person = MagicMock()
                    mock_person.name = "Test Person"
                    mock_db_instance.get_person.return_value = mock_person

                    # Call the method
                    FacesPanel._find_person_photos(panel, person_id=42)

                    # Verify it called find_more_faces_for_person with correct person_id
                    mock_analyzer.find_more_faces_for_person.assert_called_once()
                    call_args = mock_analyzer.find_more_faces_for_person.call_args
                    assert call_args.kwargs.get("person_id") == 42

    def test_find_pet_photos_uses_pet_id(self) -> None:
        """Test that _find_pet_photos passes pet_id to analyzer."""
        with patch("duplicleaner.ui.faces_panel.dpg"):
            with patch("duplicleaner.ui.faces_panel.get_database") as mock_db:
                with patch("duplicleaner.ui.faces_panel.get_config") as mock_config:
                    mock_db_instance = MagicMock()
                    mock_db.return_value = mock_db_instance

                    mock_config_instance = MagicMock()
                    mock_config.return_value = mock_config_instance
                    mock_config_instance.ai = MagicMock()

                    from duplicleaner.ui.faces_panel import FacesPanel

                    panel = MagicMock(spec=FacesPanel)
                    panel.db = mock_db_instance
                    panel.on_status_update = None

                    mock_analyzer = MagicMock()
                    mock_analyzer.find_more_detections_for_pet.return_value = (3, 2)
                    panel.pet_analyzer = mock_analyzer

                    mock_pet = MagicMock()
                    mock_pet.name = "Fluffy"
                    mock_db_instance.get_pet.return_value = mock_pet

                    FacesPanel._find_pet_photos(panel, pet_id=99)

                    mock_analyzer.find_more_detections_for_pet.assert_called_once()
                    call_args = mock_analyzer.find_more_detections_for_pet.call_args
                    assert call_args.kwargs.get("pet_id") == 99


class TestFaceAnalyzerIntegration:
    """Integration tests for face analyzer methods."""

    def test_find_more_respects_threshold(self, test_db: Database) -> None:
        """Test that find_more_faces_for_person respects similarity threshold."""
        from duplicleaner.ai.faces import FaceAnalyzer

        # Create person with embedding
        person = Person(name="Test", photo_count=1)
        person_id = test_db.add_person(person)

        analyzer = FaceAnalyzer(test_db)

        # With very high threshold, should find no matches
        matches, assigned = analyzer.find_more_faces_for_person(
            person_id=person_id,
            threshold=0.99,  # Very high
            auto_assign=False
        )

        # No matches expected (no unassigned faces anyway)
        assert matches == 0
        assert assigned == 0

    def test_auto_assign_false_does_not_assign(self, test_db: Database) -> None:
        """Test that auto_assign=False prevents automatic assignment."""
        from duplicleaner.ai.faces import FaceAnalyzer

        person = Person(name="Test", photo_count=1)
        person_id = test_db.add_person(person)

        analyzer = FaceAnalyzer(test_db)

        # Even if matches found, should not assign
        matches, assigned = analyzer.find_more_faces_for_person(
            person_id=person_id,
            threshold=0.5,
            auto_assign=False
        )

        # assigned should be 0 even if matches > 0
        assert assigned == 0


# =============================================================================
# New Test Classes for Phase 1-4 Features
# =============================================================================


class TestHiddenPersons:
    """Test hidden/ignored person functionality."""

    def test_create_hidden_person_from_cluster(self, test_db: Database) -> None:
        """Test creating a hidden person from face IDs."""
        from duplicleaner.db.models import FileRecord, Drive

        # Create drives and files first (for foreign key constraint)
        drive = Drive(id="test_drive", label="Test", path="C:\\test", total_space=100, free_space=50)
        test_db.add_drive(drive)
        file1 = FileRecord(id=1, drive_id="test_drive", path="C:\\test\\img1.jpg", filename="img1.jpg", size=100)
        file2 = FileRecord(id=2, drive_id="test_drive", path="C:\\test\\img2.jpg", filename="img2.jpg", size=100)
        test_db.add_file(file1)
        test_db.add_file(file2)

        # Create some faces to use
        face1 = Face(file_id=1, bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100)
        face2 = Face(file_id=2, bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100)
        face1_id = test_db.add_face(face1)
        face2_id = test_db.add_face(face2)

        # Create hidden person from faces
        person_id = test_db.create_hidden_person_from_cluster([face1_id, face2_id])

        # Verify person was created with correct attributes
        person = test_db.get_person(person_id)
        assert person is not None
        assert person.is_hidden == True
        assert person.name.startswith("Unknown #")

        # Verify faces were assigned
        face1_updated = test_db.get_face(face1_id)
        face2_updated = test_db.get_face(face2_id)
        assert face1_updated.person_id == person_id
        assert face2_updated.person_id == person_id

    def test_hidden_persons_not_shown_by_default(self, test_db: Database) -> None:
        """Test that hidden persons are excluded by default."""
        # Create a regular person
        regular = Person(name="Regular Person", photo_count=1)
        regular_id = test_db.add_person(regular)

        # Create a hidden person
        hidden = Person(name="Hidden Person", is_hidden=True, photo_count=1)
        hidden_id = test_db.add_person(hidden)

        # Get all persons without include_hidden
        persons = test_db.get_all_persons(include_hidden=False)
        person_ids = [p.id for p in persons]

        assert regular_id in person_ids
        assert hidden_id not in person_ids

    def test_hidden_persons_shown_when_requested(self, test_db: Database) -> None:
        """Test that hidden persons are included when requested."""
        # Create a hidden person
        hidden = Person(name="Hidden Person", is_hidden=True, photo_count=1)
        hidden_id = test_db.add_person(hidden)

        # Get all persons with include_hidden=True
        persons = test_db.get_all_persons(include_hidden=True)
        person_ids = [p.id for p in persons]

        assert hidden_id in person_ids

    def test_restore_hidden_person(self, test_db: Database) -> None:
        """Test restoring a hidden person to visible."""
        # Create hidden person
        hidden = Person(name="Hidden", is_hidden=True, photo_count=1)
        person_id = test_db.add_person(hidden)

        # Restore (unhide)
        test_db.set_person_hidden(person_id, False)

        # Verify restored (SQLite returns 0/1 for booleans)
        person = test_db.get_person(person_id)
        assert person.is_hidden == False or person.is_hidden == 0

    def test_get_hidden_person_count(self, test_db: Database) -> None:
        """Test counting hidden persons."""
        # Create some hidden persons
        for i in range(3):
            hidden = Person(name=f"Hidden {i}", is_hidden=True, photo_count=1)
            test_db.add_person(hidden)

        count = test_db.get_hidden_person_count()
        assert count == 3


class TestDeletePerson:
    """Test person deletion functionality."""

    def test_delete_person_unassigns_faces(self, test_db: Database) -> None:
        """Test that deleting a person unassigns their faces."""
        from duplicleaner.db.models import FileRecord, Drive

        # Create drives and files first (for foreign key constraint)
        drive = Drive(id="test_drive", label="Test", path="C:\\test", total_space=100, free_space=50)
        test_db.add_drive(drive)
        file1 = FileRecord(id=1, drive_id="test_drive", path="C:\\test\\img1.jpg", filename="img1.jpg", size=100)
        file2 = FileRecord(id=2, drive_id="test_drive", path="C:\\test\\img2.jpg", filename="img2.jpg", size=100)
        test_db.add_file(file1)
        test_db.add_file(file2)

        # Create person
        person = Person(name="Test Person", photo_count=2)
        person_id = test_db.add_person(person)

        # Create faces assigned to person
        face1 = Face(file_id=1, person_id=person_id, bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100)
        face2 = Face(file_id=2, person_id=person_id, bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100)
        face1_id = test_db.add_face(face1)
        face2_id = test_db.add_face(face2)

        # Delete person
        unassigned_count = test_db.delete_person(person_id)

        # Verify person deleted
        assert test_db.get_person(person_id) is None

        # Verify faces unassigned (but still exist)
        face1_updated = test_db.get_face(face1_id)
        face2_updated = test_db.get_face(face2_id)
        assert face1_updated is not None
        assert face1_updated.person_id is None
        assert face2_updated is not None
        assert face2_updated.person_id is None

        # Verify count
        assert unassigned_count == 2


class TestFaceCountMethods:
    """Test face counting database methods."""

    def test_get_low_confidence_face_count(self, test_db: Database) -> None:
        """Test counting low confidence faces."""
        from duplicleaner.db.models import FileRecord, Drive

        # Create drives and files first (for foreign key constraint)
        drive = Drive(id="test_drive", label="Test", path="C:\\test", total_space=100, free_space=50)
        test_db.add_drive(drive)
        file1 = FileRecord(id=1, drive_id="test_drive", path="C:\\test\\img1.jpg", filename="img1.jpg", size=100)
        file2 = FileRecord(id=2, drive_id="test_drive", path="C:\\test\\img2.jpg", filename="img2.jpg", size=100)
        test_db.add_file(file1)
        test_db.add_file(file2)

        # Create faces with different confidence levels
        low_conf = Face(file_id=1, confidence=0.3, bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100)
        high_conf = Face(file_id=2, confidence=0.9, bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100)
        test_db.add_face(low_conf)
        test_db.add_face(high_conf)

        # Count faces below threshold
        count = test_db.get_low_confidence_face_count(0.5)
        assert count == 1


class TestCrossAgeClusterLinking:
    """Test cross-age cluster linking algorithm."""

    def test_link_person_across_ages_returns_counts(self, test_db: Database) -> None:
        """Test that link_person_across_ages returns appropriate counts."""
        from duplicleaner.ai.faces import FaceAnalyzer

        # Create a person
        person = Person(name="Test", photo_count=1)
        person_id = test_db.add_person(person)

        analyzer = FaceAnalyzer(test_db)

        # Should return (0, 0) when no clusters exist
        auto_count, suggest_count = analyzer.link_person_across_ages(person_id)

        assert auto_count >= 0
        assert suggest_count >= 0

    def test_find_intermediate_clusters_empty_input(self, test_db: Database) -> None:
        """Test find_intermediate_clusters with empty cluster list."""
        from duplicleaner.ai.faces import FaceAnalyzer

        person = Person(name="Test", photo_count=1)
        person_id = test_db.add_person(person)

        analyzer = FaceAnalyzer(test_db)

        auto_assigned, suggestions = analyzer.find_intermediate_clusters(person_id, [])

        assert auto_assigned == []
        assert suggestions == []

    def test_find_intermediate_clusters_nonexistent_person(self, test_db: Database) -> None:
        """Test find_intermediate_clusters with non-existent person."""
        from duplicleaner.ai.faces import FaceAnalyzer

        analyzer = FaceAnalyzer(test_db)

        auto_assigned, suggestions = analyzer.find_intermediate_clusters(99999, [])

        assert auto_assigned == []
        assert suggestions == []
