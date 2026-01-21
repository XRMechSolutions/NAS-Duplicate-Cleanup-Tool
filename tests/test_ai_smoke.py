from __future__ import annotations

import pytest

from duplicleaner.ai.quality import QualityScorer, CV2_AVAILABLE
from duplicleaner.ai.ocr import OCREngine, EASYOCR_AVAILABLE


def test_quality_availability_flag(test_db) -> None:
    scorer = QualityScorer(db=test_db)
    assert scorer.is_available() is CV2_AVAILABLE


@pytest.mark.requires_cv2
def test_quality_analysis_missing_cv2(fs_tree, test_db) -> None:
    if CV2_AVAILABLE:
        pytest.skip("OpenCV available; skip missing-CV2 behavior")

    scorer = QualityScorer(db=test_db)
    result = scorer.analyze_image(str(fs_tree.files["base_img"]))
    assert result is None


def test_ocr_availability_flag(test_db) -> None:
    engine = OCREngine(db=test_db)
    assert engine.is_available() is EASYOCR_AVAILABLE


@pytest.mark.requires_easyocr
def test_ocr_missing_easyocr(fs_tree, test_db) -> None:
    if EASYOCR_AVAILABLE:
        pytest.skip("EasyOCR available; skip missing-EasyOCR behavior")

    engine = OCREngine(db=test_db)
    result = engine.extract_text(str(fs_tree.files["base_img"]))
    assert result is None
