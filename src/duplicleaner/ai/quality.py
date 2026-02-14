"""Image quality scoring module.

Uses OpenCV for blur detection, exposure analysis, and overall quality scoring.
No ML models needed - pure algorithmic approach.
"""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event

import numpy as np

from ..db.database import Database
from ..db.models import FileRecord
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import OpenCV
CV2_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    logger.warning("OpenCV not available. Quality scoring disabled.")


@dataclass
class QualityResult:
    """Quality analysis result for an image."""
    file_id: int
    overall_score: float  # 0-100
    blur_score: float     # 0-100 (higher = sharper)
    exposure_score: float # 0-100 (50 = optimal exposure)
    noise_score: float    # 0-100 (higher = less noise)
    contrast_score: float # 0-100
    is_underexposed: bool
    is_overexposed: bool
    is_blurry: bool


@dataclass
class QualityProgress:
    """Progress tracking for quality analysis."""
    total_files: int = 0
    processed_files: int = 0
    current_file: str = ""
    phase: str = "initializing"
    is_cancelled: bool = False

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class QualityScorer:
    """Image quality assessment using OpenCV algorithms."""

    # Thresholds
    BLUR_THRESHOLD = 100.0  # Laplacian variance below this = blurry
    UNDEREXPOSED_THRESHOLD = 50  # Mean brightness below this
    OVEREXPOSED_THRESHOLD = 200  # Mean brightness above this
    LOW_CONTRAST_THRESHOLD = 40  # Std dev below this

    def __init__(self, db: Database):
        """Initialize quality scorer.

        Args:
            db: Database instance
        """
        self.db = db

        # Progress tracking
        self.progress = QualityProgress()
        self._cancel_event = Event()
        self._progress_callback: Callable[[QualityProgress], None] | None = None

    def set_progress_callback(
        self, callback: Callable[[QualityProgress], None] | None
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
        """Check if OpenCV is available."""
        return CV2_AVAILABLE

    def calculate_blur_score(self, image: np.ndarray) -> tuple[float, bool]:
        """Calculate blur score using Laplacian variance.

        Args:
            image: BGR image

        Returns:
            Tuple of (score 0-100, is_blurry)
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Calculate Laplacian variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()

        # Normalize to 0-100 scale
        # Higher variance = sharper image
        # Using log scale for better distribution
        normalized = min(100.0, np.log10(variance + 1) * 25) if variance > 0 else 0.0

        is_blurry = variance < self.BLUR_THRESHOLD

        return normalized, is_blurry

    def calculate_exposure_score(
        self, image: np.ndarray
    ) -> tuple[float, bool, bool]:
        """Calculate exposure score from histogram.

        Args:
            image: BGR image

        Returns:
            Tuple of (score 0-100, is_underexposed, is_overexposed)
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Calculate mean brightness
        mean_brightness = np.mean(gray)

        # Calculate histogram spread
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist = hist.flatten()

        # Find 5th and 95th percentile
        cumsum = np.cumsum(hist)
        total = cumsum[-1]
        p5 = np.searchsorted(cumsum, total * 0.05)
        p95 = np.searchsorted(cumsum, total * 0.95)

        # Calculate exposure score
        # Optimal is around 128 (middle gray)
        deviation = abs(mean_brightness - 128)
        exposure_score = max(0, 100 - deviation * 0.8)

        # Check for clipping
        is_underexposed = mean_brightness < self.UNDEREXPOSED_THRESHOLD
        is_overexposed = mean_brightness > self.OVEREXPOSED_THRESHOLD

        # Penalize for histogram clipping
        if p5 < 10 or p95 > 245:
            exposure_score *= 0.8

        return exposure_score, is_underexposed, is_overexposed

    def calculate_contrast_score(self, image: np.ndarray) -> float:
        """Calculate contrast score.

        Args:
            image: BGR image

        Returns:
            Score 0-100
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Standard deviation of pixel values
        std_dev = np.std(gray)

        # Normalize (typical range is 20-80)
        score = min(100.0, std_dev * 1.5)

        return score

    def calculate_noise_score(self, image: np.ndarray) -> float:
        """Estimate noise level in image.

        Uses high-pass filter to detect noise.

        Args:
            image: BGR image

        Returns:
            Score 0-100 (higher = less noise)
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Difference reveals high-frequency content (noise)
        diff = cv2.absdiff(gray, blurred)
        noise_level = np.std(diff)

        # Lower noise = higher score
        # Typical noise range 0-20
        score = max(0, 100 - noise_level * 5)

        return score

    def analyze_image(self, image_path: str) -> QualityResult | None:
        """Analyze image quality.

        Args:
            image_path: Path to image file

        Returns:
            QualityResult or None on error
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available")
            return None

        try:
            # Load image
            image = cv2.imread(image_path)
            if image is None:
                logger.warning(f"Failed to load image: {image_path}")
                return None

            # Calculate individual scores
            blur_score, is_blurry = self.calculate_blur_score(image)
            exposure_score, is_underexposed, is_overexposed = self.calculate_exposure_score(image)
            contrast_score = self.calculate_contrast_score(image)
            noise_score = self.calculate_noise_score(image)

            # Calculate overall score (weighted average)
            overall = (
                blur_score * 0.35 +      # Sharpness is most important
                exposure_score * 0.30 +   # Exposure second
                contrast_score * 0.20 +   # Contrast third
                noise_score * 0.15        # Noise less visible
            )

            return QualityResult(
                file_id=0,  # Set by caller
                overall_score=overall,
                blur_score=blur_score,
                exposure_score=exposure_score,
                noise_score=noise_score,
                contrast_score=contrast_score,
                is_underexposed=is_underexposed,
                is_overexposed=is_overexposed,
                is_blurry=is_blurry,
            )

        except Exception as e:
            logger.error(f"Error analyzing {image_path}: {e}")
            return None

    def analyze_file(self, file_record: FileRecord) -> QualityResult | None:
        """Analyze a file and store results.

        Args:
            file_record: FileRecord to analyze

        Returns:
            QualityResult or None
        """
        if file_record.id is None:
            return None

        result = self.analyze_image(file_record.path)
        if not result:
            return None

        result.file_id = file_record.id

        # Update database
        self.db.update_scene_quality(
            file_record.id,
            result.overall_score,
            result.blur_score,
            result.exposure_score,
        )

        return result

    def analyze_batch(
        self,
        file_records: list[FileRecord],
        skip_existing: bool = True,
    ) -> int:
        """Analyze a batch of files.

        Args:
            file_records: Files to analyze
            skip_existing: Skip files with existing quality data

        Returns:
            Number of files analyzed
        """
        self.progress = QualityProgress(
            total_files=len(file_records),
            phase="analyzing",
        )
        self._cancel_event.clear()
        self._notify_progress()

        analyzed = 0

        for i, file_record in enumerate(file_records):
            if self._cancel_event.is_set():
                self.progress.is_cancelled = True
                break

            self.progress.current_file = file_record.path
            self.progress.processed_files = i + 1
            self._notify_progress()

            # Skip if already analyzed
            if skip_existing and file_record.id:
                existing = self.db.get_scene_analysis(file_record.id)
                if existing and existing.quality_score is not None:
                    continue

            # Analyze
            result = self.analyze_file(file_record)
            if result:
                analyzed += 1

        self.progress.phase = "complete"
        self._notify_progress()

        return analyzed

    def compare_quality(
        self,
        file_ids: list[int],
    ) -> list[tuple[int, float]]:
        """Compare quality of multiple images.

        Useful for choosing best from duplicates.

        Args:
            file_ids: List of file IDs to compare

        Returns:
            List of (file_id, score) tuples, sorted by score descending
        """
        results = []

        for file_id in file_ids:
            analysis = self.db.get_scene_analysis(file_id)
            if analysis and analysis.quality_score is not None:
                results.append((file_id, analysis.quality_score))
            else:
                # Analyze on the fly
                file_record = self.db.get_file(file_id)
                if file_record:
                    quality = self.analyze_file(file_record)
                    if quality:
                        results.append((file_id, quality.overall_score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_best_from_group(self, file_ids: list[int]) -> int | None:
        """Get the best quality image from a group.

        Args:
            file_ids: List of file IDs

        Returns:
            File ID of best quality image, or None
        """
        ranked = self.compare_quality(file_ids)
        if ranked:
            return ranked[0][0]
        return None

    def cancel(self) -> None:
        """Cancel ongoing operation."""
        self._cancel_event.set()
        logger.info("Quality analysis cancelled")
