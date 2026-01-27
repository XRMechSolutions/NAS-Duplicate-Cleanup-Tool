# tests/test_organizer_ai.py

import pytest
from unittest.mock import MagicMock, patch

from duplicleaner.core.organizer import Organizer, OrganizeSettings
from duplicleaner.db.database import get_database
from duplicleaner.db.models import SceneAnalysis, OCRResult
from tests.fixtures.fs_builder import FixturePaths

@pytest.fixture
def mock_ai_engines():
    """Mocks the AI engines to return predefined results."""
    with patch('duplicleaner.core.organizer.ObjectDetector') as MockObjectDetector, \
         patch('duplicleaner.core.organizer.OCREngine') as MockOCREngine:

        # Mock ObjectDetector
        mock_object_detector = MockObjectDetector.return_value
        mock_obj_result = MagicMock()
        mock_obj_result.unique_labels = ['dog', 'ball']
        mock_object_detector.detect_objects.return_value = mock_obj_result
        mock_object_detector.load_model.return_value = None

        # Mock OCREngine
        mock_ocr_engine = MockOCREngine.return_value
        mock_ocr_result = MagicMock()
        mock_ocr_result.full_text = "This is a test document with a lot of text."
        mock_ocr_engine.extract_text.return_value = mock_ocr_result
        mock_ocr_engine.load_model.return_value = None

        yield mock_object_detector, mock_ocr_engine

def test_organizer_with_ai_features(fs_tree: FixturePaths, mock_ai_engines):
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
    fs_tree.create_file(source_dir / "image1.jpg", "image data 1")
    fs_tree.create_file(source_dir / "doc_image.png", "image data 2")

    # 2. Run Organizer with AI settings
    settings = OrganizeSettings(
        run_object_detection=True,
        run_document_classification=True,
        move_files=False, # Use copy to easily check results
    )
    organizer = Organizer(db=db, settings=settings, object_detector=mock_object_detector, ocr_engine=mock_ocr_engine)

    # Run execute to perform the organization
    results = organizer.execute(str(source_dir), str(dest_dir))

    # 3. Assertions
    assert len(results) == 2
    
    # Find the results for each file
    result_img1 = next((r for r in results if "image1.jpg" in r.source_path), None)
    result_doc = next((r for r in results if "doc_image.png" in r.source_path), None)

    assert result_img1 is not None
    assert result_doc is not None

    # Check that AI tags and document flags are in the result
    assert result_img1.ai_tags == ['dog', 'ball']
    assert not result_img1.is_document
    assert result_doc.is_document

    # Check database for AI data
    file1_record = db.get_file_by_path_any(result_img1.dest_path)
    file2_record = db.get_file_by_path_any(result_doc.dest_path)

    assert file1_record is not None
    assert file2_record is not None

    # Check scene analysis for image1
    scene_analysis = db.get_scene_analysis(file1_record.id)
    assert scene_analysis is not None
    assert scene_analysis.objects == '["dog", "ball"]'

    # Check OCR result for doc_image
    ocr_result = db.get_ocr_result(file2_record.id)
    assert ocr_result is not None
    assert ocr_result.is_document
