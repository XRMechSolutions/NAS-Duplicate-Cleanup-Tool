"""OCR (Optical Character Recognition) module.

Uses EasyOCR to extract text from images, documents, and screenshots.
Text is indexed in ocr_fts for full-text search.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from threading import Event
from typing import Callable, Optional

from ..db.database import Database
from ..db.models import FileRecord, OCRResult
from ..utils.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import EasyOCR
EASYOCR_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    logger.warning("EasyOCR not available. OCR disabled.")


@dataclass
class OCRDetection:
    """A detected text region."""
    text: str
    confidence: float
    bbox: list[list[int]]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]


@dataclass
class OCRAnalysisResult:
    """Result of OCR analysis for an image."""
    file_id: int
    full_text: str
    detections: list[OCRDetection]
    average_confidence: float
    language: str


@dataclass
class OCRProgress:
    """Progress tracking for OCR analysis."""
    total_files: int = 0
    processed_files: int = 0
    characters_extracted: int = 0
    current_file: str = ""
    phase: str = "initializing"
    is_cancelled: bool = False

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class OCREngine:
    """Text extraction from images using EasyOCR."""

    # Supported languages (common subset)
    DEFAULT_LANGUAGES = ["en"]
    SUPPORTED_LANGUAGES = [
        "en",  # English
        "es",  # Spanish
        "fr",  # French
        "de",  # German
        "it",  # Italian
        "pt",  # Portuguese
        "nl",  # Dutch
        "pl",  # Polish
        "ru",  # Russian
        "zh_sim",  # Chinese Simplified
        "zh_tra",  # Chinese Traditional
        "ja",  # Japanese
        "ko",  # Korean
        "ar",  # Arabic
    ]

    def __init__(
        self,
        db: Database,
        languages: Optional[list[str]] = None,
        use_gpu: bool = True,
    ):
        """Initialize OCR engine.

        Args:
            db: Database instance
            languages: Languages to detect (default: English only)
            use_gpu: Whether to use GPU
        """
        self.db = db
        self.languages = languages or self.DEFAULT_LANGUAGES.copy()
        self.use_gpu = use_gpu

        self._reader: Optional["easyocr.Reader"] = None
        self._model_loaded = False

        # Progress tracking
        self.progress = OCRProgress()
        self._cancel_event = Event()
        self._progress_callback: Optional[Callable[[OCRProgress], None]] = None

    def set_progress_callback(
        self, callback: Optional[Callable[[OCRProgress], None]]
    ) -> None:
        """Set callback for progress updates."""
        self._progress_callback = callback

    def _notify_progress(self) -> None:
        """Notify callback of progress update."""
        if self._progress_callback:
            try:
                self._progress_callback(self.progress)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    def is_available(self) -> bool:
        """Check if EasyOCR is available."""
        return EASYOCR_AVAILABLE

    def load_model(self) -> bool:
        """Load the OCR model.

        Returns:
            True if loaded successfully
        """
        if not EASYOCR_AVAILABLE:
            logger.error("EasyOCR not installed")
            return False

        if self._model_loaded:
            return True

        try:
            self.progress.phase = "loading_model"
            self._notify_progress()

            logger.info(f"Loading EasyOCR for languages: {self.languages}")

            # Get model directory
            config = get_config()
            model_dir = config.ai.models_directory
            if not model_dir:
                model_dir = os.path.join(os.path.expanduser("~"), ".duplicleaner", "models", "easyocr")

            os.makedirs(model_dir, exist_ok=True)

            # Create reader
            self._reader = easyocr.Reader(
                self.languages,
                gpu=self.use_gpu,
                model_storage_directory=model_dir,
                download_enabled=True,
            )

            self._model_loaded = True
            logger.info("EasyOCR model loaded")
            return True

        except Exception as e:
            logger.error(f"Failed to load EasyOCR: {e}")
            self._reader = None
            self._model_loaded = False
            return False

    def unload_model(self) -> None:
        """Unload model to free memory."""
        self._reader = None
        self._model_loaded = False
        logger.info("EasyOCR model unloaded")

    def extract_text(self, image_path: str) -> Optional[OCRAnalysisResult]:
        """Extract text from an image.

        Args:
            image_path: Path to image file

        Returns:
            OCRAnalysisResult or None on error
        """
        if not self._model_loaded:
            if not self.load_model():
                return None

        try:
            # Run OCR
            results = self._reader.readtext(image_path)

            if not results:
                return OCRAnalysisResult(
                    file_id=0,
                    full_text="",
                    detections=[],
                    average_confidence=0.0,
                    language=self.languages[0],
                )

            # Process detections
            detections = []
            texts = []
            total_confidence = 0.0

            for bbox, text, confidence in results:
                detections.append(OCRDetection(
                    text=text,
                    confidence=confidence,
                    bbox=[[int(p[0]), int(p[1])] for p in bbox],
                ))
                texts.append(text)
                total_confidence += confidence

            # Combine text
            full_text = " ".join(texts)
            avg_confidence = total_confidence / len(detections) if detections else 0.0

            return OCRAnalysisResult(
                file_id=0,  # Set by caller
                full_text=full_text,
                detections=detections,
                average_confidence=avg_confidence,
                language=self.languages[0],
            )

        except Exception as e:
            logger.error(f"Error extracting text from {image_path}: {e}")
            return None

    def analyze_file(self, file_record: FileRecord) -> Optional[OCRResult]:
        """Analyze a file and store OCR results.

        Args:
            file_record: FileRecord to analyze

        Returns:
            OCRResult or None
        """
        if file_record.id is None:
            return None

        result = self.extract_text(file_record.path)
        if not result:
            return None

        # Skip if no text found
        if not result.full_text.strip():
            return None

        # Create OCR result
        ocr_result = OCRResult(
            file_id=file_record.id,
            extracted_text=result.full_text,
            confidence=result.average_confidence,
            language=result.language,
            created_at=datetime.now(),
        )

        # Store in database (triggers FTS5 indexing)
        self.db.add_ocr_result(ocr_result)

        return ocr_result

    def analyze_batch(
        self,
        file_records: list[FileRecord],
        skip_existing: bool = True,
    ) -> int:
        """Analyze a batch of files.

        Args:
            file_records: Files to analyze
            skip_existing: Skip files with existing OCR data

        Returns:
            Number of files with extracted text
        """
        self.progress = OCRProgress(
            total_files=len(file_records),
            phase="extracting",
        )
        self._cancel_event.clear()
        self._notify_progress()

        analyzed = 0
        total_chars = 0

        for i, file_record in enumerate(file_records):
            if self._cancel_event.is_set():
                self.progress.is_cancelled = True
                break

            self.progress.current_file = file_record.path
            self.progress.processed_files = i + 1
            self._notify_progress()

            # Skip if already analyzed
            if skip_existing and file_record.id:
                existing = self.db.get_ocr_result(file_record.id)
                if existing:
                    continue

            # Analyze
            result = self.analyze_file(file_record)
            if result:
                analyzed += 1
                total_chars += len(result.extracted_text)
                self.progress.characters_extracted = total_chars

        self.progress.phase = "complete"
        self._notify_progress()

        return analyzed

    def search_text(self, query: str, limit: int = 100) -> list[tuple[int, str]]:
        """Search for files containing text.

        Uses FTS5 full-text search.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of (file_id, matched_text) tuples
        """
        return self.db.search_ocr_text(query, limit=limit)

    def add_language(self, language: str) -> bool:
        """Add a language to detect.

        Requires model reload.

        Args:
            language: Language code (e.g., "es", "fr")

        Returns:
            True if language is supported
        """
        if language not in self.SUPPORTED_LANGUAGES:
            logger.warning(f"Unsupported language: {language}")
            return False

        if language not in self.languages:
            self.languages.append(language)
            self._model_loaded = False  # Force reload
            logger.info(f"Added language: {language}")

        return True

    def remove_language(self, language: str) -> None:
        """Remove a language.

        Requires model reload.

        Args:
            language: Language code to remove
        """
        if language in self.languages and len(self.languages) > 1:
            self.languages.remove(language)
            self._model_loaded = False
            logger.info(f"Removed language: {language}")

    def cancel(self) -> None:
        """Cancel ongoing operation."""
        self._cancel_event.set()
        logger.info("OCR analysis cancelled")
