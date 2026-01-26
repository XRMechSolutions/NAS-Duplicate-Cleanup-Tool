"""Pet detection and tracking module.

Uses YOLO for pet detection and custom algorithms for pet matching
across time, including life stage progression tracking.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Event
from typing import Callable, Optional

import numpy as np

from ..db.database import Database
from ..db.models import Pet, PetDetection, PetAgeStage, FileRecord
from ..utils.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import AI libraries
YOLO_AVAILABLE = False
CV2_AVAILABLE = False
SKLEARN_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    logger.warning("Ultralytics YOLO not available. Pet detection disabled.")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    logger.warning("OpenCV not available. Pet features limited.")

try:
    from sklearn.cluster import DBSCAN
    SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning("scikit-learn not available. Pet clustering disabled.")


# YOLO class IDs for animals (COCO dataset)
ANIMAL_CLASSES = {
    15: "bird",
    16: "cat",
    17: "dog",
    18: "horse",
    19: "sheep",
    20: "cow",
    21: "elephant",
    22: "bear",
    23: "zebra",
    24: "giraffe",
}

# Common pet species
PET_SPECIES = {"dog", "cat", "bird", "fish", "rabbit", "hamster", "guinea pig"}


@dataclass
class DetectedPet:
    """A pet detected in an image."""
    bbox: tuple[int, int, int, int]  # x, y, width, height
    species: str
    confidence: float
    breed: Optional[str] = None
    color_histogram: Optional[np.ndarray] = None
    visual_embedding: Optional[np.ndarray] = None


@dataclass
class PetMatch:
    """Result of matching a detection to a known pet."""
    pet_id: int
    pet_name: Optional[str]
    similarity: float
    color_match: float
    temporal_score: float


@dataclass
class PetCluster:
    """A cluster of similar pet detections."""
    cluster_id: int
    detection_ids: list[int]
    sample_detections: list[PetDetection]
    species: str
    avg_color_histogram: Optional[np.ndarray] = None
    pet_id: Optional[int] = None
    pet_name: Optional[str] = None


@dataclass
class PetAnalysisProgress:
    """Progress tracking for pet analysis."""
    total_files: int = 0
    processed_files: int = 0
    pets_detected: int = 0
    pets_matched: int = 0
    current_file: str = ""
    phase: str = "initializing"
    is_cancelled: bool = False

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class PetAnalyzer:
    """Pet detection, tracking, and clustering engine."""

    # YOLO model name
    DEFAULT_MODEL = "yolov8n.pt"

    # Similarity thresholds
    MATCH_THRESHOLD_HIGH = 0.85
    MATCH_THRESHOLD_MEDIUM = 0.7
    MATCH_THRESHOLD_LOW = 0.5

    # Color histogram bins
    HIST_BINS = 32

    # DBSCAN parameters
    DBSCAN_EPS = 0.4
    DBSCAN_MIN_SAMPLES = 2

    def __init__(
        self,
        db: Database,
        model_name: str = DEFAULT_MODEL,
        use_gpu: bool = True,
        confidence_threshold: float = 0.5,
    ):
        """Initialize pet analyzer.

        Args:
            db: Database instance
            model_name: YOLO model name
            use_gpu: Whether to use GPU acceleration
            confidence_threshold: Minimum detection confidence
        """
        self.db = db
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold

        self._model: Optional["YOLO"] = None
        self._model_loaded = False

        # Progress tracking
        self.progress = PetAnalysisProgress()
        self._cancel_event = Event()
        self._progress_callback: Optional[Callable[[PetAnalysisProgress], None]] = None

        # Cache for pet data
        self._pet_histograms: dict[int, np.ndarray] = {}

    def set_progress_callback(
        self, callback: Optional[Callable[[PetAnalysisProgress], None]]
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
        """Check if pet detection is available."""
        return YOLO_AVAILABLE and CV2_AVAILABLE

    def load_model(self) -> bool:
        """Load the YOLO model.

        Returns:
            True if model loaded successfully
        """
        if not YOLO_AVAILABLE:
            logger.error("YOLO not installed")
            return False

        if self._model_loaded:
            return True

        try:
            self.progress.phase = "loading_model"
            self._notify_progress()

            # Get model directory
            config = get_config()
            model_dir = config.ai.models_directory
            if not model_dir:
                model_dir = os.path.join(os.path.expanduser("~"), ".duplicleaner", "models")

            os.makedirs(model_dir, exist_ok=True)

            # Load YOLO model
            model_path = os.path.join(model_dir, self.model_name)
            self._model = YOLO(model_path if os.path.exists(model_path) else self.model_name)

            # Set device
            device = "cuda" if self.use_gpu else "cpu"
            self._model.to(device)

            self._model_loaded = True
            logger.info(f"Loaded pet detection model: {self.model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self._model = None
            self._model_loaded = False
            return False

    def unload_model(self) -> None:
        """Unload the model to free memory."""
        self._model = None
        self._model_loaded = False
        logger.info("Pet detection model unloaded")

    # ==========================================================================
    # Pet Detection
    # ==========================================================================

    def detect_pets(self, image_path: str) -> list[DetectedPet]:
        """Detect pets in an image.

        Args:
            image_path: Path to image file

        Returns:
            List of detected pets
        """
        if not self._model_loaded:
            if not self.load_model():
                return []

        if not CV2_AVAILABLE:
            return []

        try:
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                logger.warning(f"Could not read image: {image_path}")
                return []

            # Run detection
            results = self._model(img, verbose=False)

            detected = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get class
                    cls_id = int(box.cls[0])
                    if cls_id not in ANIMAL_CLASSES:
                        continue

                    species = ANIMAL_CLASSES[cls_id]
                    confidence = float(box.conf[0])

                    if confidence < self.confidence_threshold:
                        continue

                    # Get bounding box
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    x, y = int(x1), int(y1)
                    w, h = int(x2 - x1), int(y2 - y1)

                    # Extract region for color histogram
                    pet_region = img[y:y+h, x:x+w]
                    color_hist = self._compute_color_histogram(pet_region)

                    detected.append(DetectedPet(
                        bbox=(x, y, w, h),
                        species=species,
                        confidence=confidence,
                        color_histogram=color_hist,
                    ))

            return detected

        except Exception as e:
            logger.error(f"Error detecting pets in {image_path}: {e}")
            return []

    def _compute_color_histogram(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Compute color histogram for an image region.

        Args:
            image: BGR image array

        Returns:
            Normalized histogram or None
        """
        if image is None or image.size == 0:
            return None

        try:
            # Convert to HSV for better color representation
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

            # Compute histogram
            hist = cv2.calcHist(
                [hsv], [0, 1], None,
                [self.HIST_BINS, self.HIST_BINS],
                [0, 180, 0, 256]
            )

            # Normalize
            cv2.normalize(hist, hist)
            return hist.flatten()

        except Exception as e:
            logger.warning(f"Error computing color histogram: {e}")
            return None

    def _serialize_histogram(self, hist: np.ndarray) -> bytes:
        """Serialize histogram to bytes."""
        return hist.astype(np.float32).tobytes()

    def _deserialize_histogram(self, data: bytes) -> np.ndarray:
        """Deserialize histogram from bytes."""
        return np.frombuffer(data, dtype=np.float32)

    def analyze_file(self, file_record: FileRecord) -> list[PetDetection]:
        """Analyze a file for pets and store results.

        Args:
            file_record: FileRecord to analyze

        Returns:
            List of PetDetection objects stored in database
        """
        if file_record.id is None:
            return []

        # Detect pets
        detected = self.detect_pets(file_record.path)
        if not detected:
            return []

        detections = []
        for det in detected:
            # Estimate age stage based on size (rough heuristic)
            age_stage = self._estimate_age_stage(det)

            # Create PetDetection object
            detection = PetDetection(
                file_id=file_record.id,
                species=det.species,
                breed=det.breed,
                bbox_x=det.bbox[0],
                bbox_y=det.bbox[1],
                bbox_w=det.bbox[2],
                bbox_h=det.bbox[3],
                confidence=det.confidence,
                color_histogram=self._serialize_histogram(det.color_histogram) if det.color_histogram is not None else None,
                estimated_age_stage=age_stage,
            )

            # Store in database
            det_id = self.db.add_pet_detection(detection)
            detection.id = det_id
            detections.append(detection)

        return detections

    def _estimate_age_stage(self, detected: DetectedPet) -> Optional[PetAgeStage]:
        """Estimate pet age stage based on detection size.

        This is a rough heuristic - smaller pets relative to frame
        are more likely to be young.
        """
        # Get relative size
        area = detected.bbox[2] * detected.bbox[3]

        # Very rough heuristic - could be improved with ML
        if detected.species == "dog":
            if area < 5000:
                return PetAgeStage.BABY
            elif area < 15000:
                return PetAgeStage.YOUNG
            elif area < 40000:
                return PetAgeStage.ADULT
            else:
                return PetAgeStage.ADULT
        elif detected.species == "cat":
            if area < 3000:
                return PetAgeStage.BABY
            elif area < 10000:
                return PetAgeStage.YOUNG
            else:
                return PetAgeStage.ADULT

        return None

    def analyze_batch(
        self,
        file_records: list[FileRecord],
        skip_existing: bool = True,
    ) -> int:
        """Analyze a batch of files for pets.

        Args:
            file_records: List of files to analyze
            skip_existing: Skip files that already have pet data

        Returns:
            Number of pets detected
        """
        self.progress = PetAnalysisProgress(
            total_files=len(file_records),
            phase="detecting",
        )
        self._cancel_event.clear()
        self._notify_progress()

        total_pets = 0

        for i, file_record in enumerate(file_records):
            if self._cancel_event.is_set():
                self.progress.is_cancelled = True
                break

            self.progress.current_file = file_record.path
            self.progress.processed_files = i + 1
            self._notify_progress()

            # Skip if already analyzed
            if skip_existing and file_record.id:
                existing = self.db.get_pet_detections_for_file(file_record.id)
                if existing:
                    continue

            # Analyze
            detections = self.analyze_file(file_record)
            total_pets += len(detections)
            self.progress.pets_detected = total_pets

        self.progress.phase = "complete"
        self._notify_progress()

        return total_pets

    # ==========================================================================
    # Pet Matching
    # ==========================================================================

    def compare_histograms(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        """Compare two color histograms using correlation.

        Args:
            hist1: First histogram
            hist2: Second histogram

        Returns:
            Similarity score (0-1)
        """
        if hist1 is None or hist2 is None:
            return 0.0

        # Use correlation comparison
        corr = cv2.compareHist(
            hist1.reshape(-1, 1).astype(np.float32),
            hist2.reshape(-1, 1).astype(np.float32),
            cv2.HISTCMP_CORREL
        )
        # Normalize to 0-1 range
        return max(0.0, (corr + 1) / 2)

    def load_pet_histograms(self) -> None:
        """Load all pet color histograms into cache."""
        self._pet_histograms.clear()

        pets = self.db.get_all_pets()
        for pet in pets:
            if pet.id is None:
                continue

            # Get all detections for this pet
            detections = self.db.get_pet_detections_for_pet(pet.id)

            # Average the histograms
            histograms = []
            for det in detections:
                if det.color_histogram:
                    hist = self._deserialize_histogram(det.color_histogram)
                    histograms.append(hist)

            if histograms:
                avg_hist = np.mean(histograms, axis=0)
                self._pet_histograms[pet.id] = avg_hist

    def match_detection(
        self,
        detection: PetDetection,
        threshold: float = MATCH_THRESHOLD_MEDIUM,
    ) -> Optional[PetMatch]:
        """Try to match a detection to a known pet.

        Args:
            detection: Detection to match
            threshold: Minimum similarity threshold

        Returns:
            PetMatch if found, None otherwise
        """
        if not detection.color_histogram:
            return None

        if not self._pet_histograms:
            self.load_pet_histograms()

        det_hist = self._deserialize_histogram(detection.color_histogram)

        best_match: Optional[PetMatch] = None
        best_score = threshold

        for pet_id, pet_hist in self._pet_histograms.items():
            # Get pet species
            pet = self.db.get_pet(pet_id)
            if not pet:
                continue

            # Species must match
            if pet.species and pet.species != detection.species:
                continue

            # Compare histograms
            color_match = self.compare_histograms(det_hist, pet_hist)

            # Calculate overall score (can add more factors)
            score = color_match

            if score > best_score:
                best_score = score
                best_match = PetMatch(
                    pet_id=pet_id,
                    pet_name=pet.name,
                    similarity=score,
                    color_match=color_match,
                    temporal_score=0.0,  # Could add temporal factor
                )

        return best_match

    def match_and_assign_detections(
        self,
        detections: Optional[list[PetDetection]] = None,
        threshold: float = MATCH_THRESHOLD_HIGH,
        auto_assign: bool = True,
    ) -> tuple[int, int]:
        """Match unassigned detections to known pets.

        Args:
            detections: Detections to match (if None, gets unassigned from DB)
            threshold: Minimum similarity for auto-assignment
            auto_assign: Whether to automatically assign matches

        Returns:
            Tuple of (matches_found, detections_assigned)
        """
        if detections is None:
            detections = self.db.get_unassigned_pet_detections()

        self.progress.phase = "matching"
        self._notify_progress()

        matches_found = 0
        assigned = 0

        for detection in detections:
            if self._cancel_event.is_set():
                break

            match = self.match_detection(detection, threshold)
            if match:
                matches_found += 1

                if auto_assign and match.similarity >= threshold:
                    self.db.assign_pet_detection_to_pet(detection.id, match.pet_id)
                    assigned += 1
                    self.db.update_pet_photo_count(match.pet_id)

        self.progress.pets_matched = assigned
        self._notify_progress()

        return matches_found, assigned

    def find_more_detections_for_pet(
        self,
        pet_id: int,
        threshold: float = MATCH_THRESHOLD_HIGH,
        auto_assign: bool = True,
    ) -> tuple[int, int]:
        """Find and assign unassigned detections that match a specific pet.

        Unlike match_and_assign_detections which matches against all pets,
        this method only looks for detections that match the specified pet.

        Args:
            pet_id: ID of the pet to find more detections for
            threshold: Minimum similarity threshold
            auto_assign: Whether to automatically assign matching detections

        Returns:
            Tuple of (matches_found, detections_assigned)
        """
        # Get pet info
        pet = self.db.get_pet(pet_id)
        if not pet:
            logger.warning(f"Pet {pet_id} not found")
            return 0, 0

        if pet_id not in self._pet_histograms:
            self.load_pet_histograms()

        if pet_id not in self._pet_histograms:
            logger.warning(f"No histogram found for pet {pet_id}")
            return 0, 0

        pet_hist = self._pet_histograms[pet_id]

        # Get unassigned detections
        detections = self.db.get_unassigned_pet_detections()

        self.progress.phase = "matching"
        self._notify_progress()

        matches_found = 0
        assigned = 0

        for detection in detections:
            if self._cancel_event.is_set():
                break

            if not detection.color_histogram:
                continue

            # Species must match
            if pet.species and pet.species != detection.species:
                continue

            det_hist = self._deserialize_histogram(detection.color_histogram)
            score = self.compare_histograms(det_hist, pet_hist)

            if score >= threshold:
                matches_found += 1

                if auto_assign:
                    self.db.assign_pet_detection_to_pet(detection.id, pet_id)
                    assigned += 1
                    self.db.update_pet_photo_count(pet_id)

        self.progress.pets_matched = assigned
        self._notify_progress()

        logger.info(f"Found {matches_found} matches for pet {pet_id} ({pet.name}), assigned {assigned}")
        return matches_found, assigned

    # ==========================================================================
    # Pet Clustering
    # ==========================================================================

    def cluster_detections(
        self,
        species: Optional[str] = None,
        eps: float = DBSCAN_EPS,
        min_samples: int = DBSCAN_MIN_SAMPLES,
    ) -> list[PetCluster]:
        """Cluster unassigned pet detections.

        Args:
            species: Filter by species (None for all)
            eps: DBSCAN epsilon parameter
            min_samples: Minimum samples for a cluster

        Returns:
            List of PetCluster objects
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for clustering")
            return []

        # Get unassigned detections
        detections = self.db.get_unassigned_pet_detections()

        # Filter by species if specified
        if species:
            detections = [d for d in detections if d.species == species]

        if len(detections) < min_samples:
            return []

        self.progress.phase = "clustering"
        self._notify_progress()

        # Group by species first
        by_species: dict[str, list[PetDetection]] = {}
        for det in detections:
            if det.species not in by_species:
                by_species[det.species] = []
            by_species[det.species].append(det)

        clusters = []
        cluster_id = 0

        for species_name, species_detections in by_species.items():
            if len(species_detections) < min_samples:
                continue

            # Extract histograms
            histograms = []
            valid_detections = []
            for det in species_detections:
                if det.color_histogram:
                    hist = self._deserialize_histogram(det.color_histogram)
                    histograms.append(hist)
                    valid_detections.append(det)

            if len(histograms) < min_samples:
                continue

            # Compute distance matrix
            X = np.array(histograms)
            n = len(X)
            distance_matrix = np.zeros((n, n))

            for i in range(n):
                for j in range(i + 1, n):
                    similarity = self.compare_histograms(X[i], X[j])
                    distance = 1 - similarity
                    distance_matrix[i, j] = distance
                    distance_matrix[j, i] = distance

            # Run DBSCAN
            clustering = DBSCAN(
                eps=eps,
                min_samples=min_samples,
                metric="precomputed",
            ).fit(distance_matrix)

            # Build clusters
            labels = clustering.labels_
            unique_labels = set(labels)
            unique_labels.discard(-1)

            for label in unique_labels:
                indices = np.where(labels == label)[0]
                cluster_dets = [valid_detections[i] for i in indices]
                cluster_hists = [histograms[i] for i in indices]

                avg_hist = np.mean(cluster_hists, axis=0) if cluster_hists else None

                cluster = PetCluster(
                    cluster_id=cluster_id,
                    detection_ids=[d.id for d in cluster_dets if d.id is not None],
                    sample_detections=cluster_dets[:5],
                    species=species_name,
                    avg_color_histogram=avg_hist,
                )
                clusters.append(cluster)
                cluster_id += 1

        logger.info(f"Created {len(clusters)} pet clusters")
        return clusters

    # ==========================================================================
    # Pet Management
    # ==========================================================================

    def create_pet_from_cluster(
        self,
        cluster: PetCluster,
        name: str,
        breed: Optional[str] = None,
        birth_year: Optional[int] = None,
        color_pattern: Optional[str] = None,
    ) -> Optional[int]:
        """Create a pet from a detection cluster.

        Args:
            cluster: PetCluster to convert
            name: Name for the pet
            breed: Optional breed
            birth_year: Optional birth year
            color_pattern: Optional description of markings

        Returns:
            Pet ID if created
        """
        # Create pet
        pet = Pet(
            name=name,
            species=cluster.species,
            breed=breed,
            birth_year=birth_year,
            color_pattern=color_pattern,
            photo_count=len(cluster.detection_ids),
        )

        # Get reference photo
        if cluster.sample_detections:
            ref_det = cluster.sample_detections[0]
            pet.reference_photo_id = ref_det.file_id

        pet_id = self.db.add_pet(pet)

        # Assign all detections to pet
        for det_id in cluster.detection_ids:
            self.db.assign_pet_detection_to_pet(det_id, pet_id)

        # Refresh cache
        self.load_pet_histograms()

        logger.info(f"Created pet '{name}' ({cluster.species}) with {len(cluster.detection_ids)} photos")
        return pet_id

    def get_pet_timeline(
        self,
        pet_id: int,
    ) -> list[tuple[int, list[PetDetection]]]:
        """Get pet detections organized by year.

        Args:
            pet_id: Pet to get timeline for

        Returns:
            List of (year, detections) tuples
        """
        detections = self.db.get_pet_detections_for_pet(pet_id)

        # Group by year
        by_year: dict[int, list[PetDetection]] = {}
        for det in detections:
            file_record = self.db.get_file(det.file_id)
            if file_record and file_record.modified:
                year = file_record.modified.year
                if year not in by_year:
                    by_year[year] = []
                by_year[year].append(det)

        return sorted(by_year.items())

    def cancel(self) -> None:
        """Cancel ongoing operation."""
        self._cancel_event.set()
        logger.info("Pet analysis cancelled")
