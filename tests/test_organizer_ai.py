# tests/test_organizer_ai.py

from unittest.mock import MagicMock, patch

import pytest

from duplicleaner.core.organizer import Organizer, OrganizeSettings
from duplicleaner.db.database import get_database
from duplicleaner.db.models import Drive
from tests.fixtures.fs_builder import FixturePaths


@pytest.fixture
def mock_ai_engines():
    """Mocks the AI engines to return predefined results based on file path."""
    with patch('duplicleaner.core.organizer.ObjectDetector') as MockObjectDetector, \
         patch('duplicleaner.core.organizer.OCREngine') as MockOCREngine:

        mock_object_detector = MockObjectDetector.return_value
        mock_ocr_engine = MockOCREngine.return_value

        def mock_detect_objects(file_path):
            if "image1.jpg" in file_path:
                mock_obj_result = MagicMock()
                mock_obj_result.unique_labels = ['dog', 'ball']
                return mock_obj_result
            return None # No objects for doc_image.png

        def mock_extract_text(file_path):
            if "doc_image.png" in file_path:
                mock_ocr_result = MagicMock()
                mock_ocr_result.full_text = (
                    "This is a test document with a lot of text, exceeding 100 characters "
                    "for classification. Additional text to ensure the length passes the threshold."
                )
                return mock_ocr_result
            return None # No OCR for image1.jpg

        mock_object_detector.detect_objects.side_effect = mock_detect_objects
        mock_object_detector.load_model.return_value = None

        mock_ocr_engine.extract_text.side_effect = mock_extract_text
        mock_ocr_engine.load_model.return_value = None

        yield mock_object_detector, mock_ocr_engine

def test_organizer_with_ai_features(fs_tree: FixturePaths, mock_ai_engines, tmp_path):
    """
    Tests that the Organizer correctly uses AI features to generate tags
    and classifications and saves them to the database.
    """
    # 1. Setup
    db = get_database()
    mock_object_detector, mock_ocr_engine = mock_ai_engines

    # Create test files
    source_dir = fs_tree.root / "source"
    dest_dir = fs_tree.root / "dest"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "image1.jpg").write_bytes(b"image data 1")
    (source_dir / "doc_image.png").write_bytes(b"image data 2")
    (source_dir / "clip1.mp4").write_bytes(b"video data 3")

    # Register drive for organizer DB updates
    db.add_drive(Drive(id="D1", label="TestDrive", path=str(fs_tree.root)))

    # 2. Run Organizer with AI settings
    settings = OrganizeSettings(
        run_object_detection=True,
        run_document_classification=True,
        move_files=False, # Use copy to easily check results
    )
    organizer = Organizer(db=db, settings=settings, object_detector=mock_object_detector, ocr_engine=mock_ocr_engine)

    frame_path = tmp_path / "frame_image1.jpg"
    frame_path.write_bytes(b"frame data")
    with patch.object(Organizer, "_extract_video_frame_image", return_value=str(frame_path)):
        # Run execute to perform the organization
        results = organizer.execute(str(source_dir), str(dest_dir))

    # 3. Assertions
    assert len(results) == 3

    # Find the results for each file
    result_img1 = next((r for r in results if "image1.jpg" in r.source_path), None)
    result_doc = next((r for r in results if "doc_image.png" in r.source_path), None)
    result_video = next((r for r in results if "clip1.mp4" in r.source_path), None)

    assert result_img1 is not None
    assert result_doc is not None
    assert result_video is not None

    # Check that AI tags and document flags are in the result
    # For image1.jpg (photo)
    assert result_img1.ai_tags == ['dog', 'ball']
    assert not result_img1.is_document

    # For doc_image.png (document)
    assert result_doc.ai_tags == []
    assert result_doc.is_document
    assert result_video.ai_tags == ['dog', 'ball']
    assert not result_video.is_document

    # Check database for AI data
    file1_record = db.get_file_by_path_any(result_img1.dest_path)
    file2_record = db.get_file_by_path_any(result_doc.dest_path)

    assert file1_record is not None
    assert file2_record is not None

    # Check scene analysis for image1
    scene_analysis_img1 = db.get_scene_analysis(file1_record.id)
    assert scene_analysis_img1 is not None
    assert scene_analysis_img1.objects == '["dog", "ball"]'

    # Check OCR result for doc_image
    ocr_result_doc = db.get_ocr_result(file2_record.id)
    assert ocr_result_doc is not None
    assert ocr_result_doc.extracted_text == ""  # Stored as document flag only for now

    # Verify that object detection was NOT called for doc_image.png
    mock_object_detector.detect_objects.assert_any_call(str(source_dir / "image1.jpg"))
    assert mock_object_detector.detect_objects.call_count == 2  # image + video frame

    # Verify that OCR was called for both, but only resulted in document for doc_image.png
    mock_ocr_engine.extract_text.assert_any_call(str(source_dir / "image1.jpg"))
    mock_ocr_engine.extract_text.assert_any_call(str(source_dir / "doc_image.png"))
    assert mock_ocr_engine.extract_text.call_count == 2
