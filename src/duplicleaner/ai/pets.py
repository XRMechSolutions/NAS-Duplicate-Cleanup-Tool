"""Pet detection and tracking module.

Uses YOLO for pet detection, CLIP for visual embeddings and breed
classification, and temporal bridging for tracking pets across years.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from threading import Event

import numpy as np

from ..db.database import Database
from ..db.models import FileRecord, Pet, PetAgeStage, PetDetection
from ..utils.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Register HEIC/HEIF support for PIL
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    logger.debug("HEIC/HEIF support enabled via pillow-heif")
except ImportError:
    logger.debug("pillow-heif not available - HEIC files will not be readable")

# Try to import AI libraries
YOLO_AVAILABLE = False
CV2_AVAILABLE = False
SKLEARN_AVAILABLE = False
CLIP_AVAILABLE = False
TORCH_AVAILABLE = False
PIL_AVAILABLE = False

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

try:
    import open_clip
    import torch
    CLIP_AVAILABLE = True
    TORCH_AVAILABLE = True
except ImportError:
    logger.debug("open-clip/torch not available. Visual embeddings disabled.")

try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    logger.debug("PIL not available. Some pet features limited.")


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

# Common household pets only (excludes wild animals to reduce false positives)
COMMON_PETS_ONLY = {
    15: "bird",
    16: "cat",
    17: "dog",
}

# Common pet species
PET_SPECIES = {"dog", "cat", "bird", "fish", "rabbit", "hamster", "guinea pig"}

# CLIP zero-shot breed classification labels
DOG_BREEDS = [
    "Labrador Retriever", "Golden Retriever", "German Shepherd",
    "French Bulldog", "Bulldog", "Poodle", "Beagle", "Rottweiler",
    "Dachshund", "Yorkshire Terrier", "Boxer", "Siberian Husky",
    "Great Dane", "Doberman Pinscher", "Australian Shepherd",
    "Cavalier King Charles Spaniel", "Shih Tzu", "Boston Terrier",
    "Bernese Mountain Dog", "Pomeranian", "Havanese", "Cocker Spaniel",
    "Border Collie", "Chihuahua", "Corgi", "Maltese", "Pit Bull",
    "Schnauzer", "Shetland Sheepdog", "Jack Russell Terrier",
    "Akita", "Dalmatian", "Samoyed", "Weimaraner", "Bichon Frise",
    "Pug", "Vizsla", "Whippet", "Greyhound", "Irish Setter",
]

CAT_BREEDS = [
    "Persian", "Siamese", "Maine Coon", "Ragdoll", "Bengal",
    "British Shorthair", "Abyssinian", "Scottish Fold", "Sphynx",
    "Russian Blue", "Birman", "Norwegian Forest Cat", "Savannah",
    "Devon Rex", "Burmese", "Tonkinese", "American Shorthair",
    "Turkish Angora", "Oriental Shorthair", "Exotic Shorthair",
    "Tabby", "Calico", "Tuxedo", "Orange Tabby", "Black Cat",
]

BIRD_BREEDS = [
    "Parakeet", "Cockatiel", "African Grey Parrot", "Cockatoo",
    "Macaw", "Lovebird", "Canary", "Finch", "Conure", "Amazon Parrot",
]

# Dominant color labels for pet marking analysis
PET_COLOR_LABELS = [
    "black", "white", "brown", "golden", "cream", "grey", "red",
    "orange", "tan", "brindle", "spotted", "merle", "tricolor",
    "black and white", "brown and white", "black and tan",
]


@dataclass
class DetectedPet:
    """A pet detected in an image."""
    bbox: tuple[int, int, int, int]  # x, y, width, height
    species: str
    confidence: float
    breed: str | None = None
    breed_confidence: float = 0.0
    color_histogram: np.ndarray | None = None
    visual_embedding: np.ndarray | None = None
    dominant_colors: list[str] = field(default_factory=list)


@dataclass
class PetMatch:
    """Result of matching a detection to a known pet."""
    pet_id: int
    pet_name: str | None
    similarity: float
    color_match: float
    embedding_match: float
    breed_match: float
    temporal_score: float


@dataclass
class PetCluster:
    """A cluster of similar pet detections."""
    cluster_id: int
    detection_ids: list[int]
    sample_detections: list[PetDetection]
    species: str
    avg_color_histogram: np.ndarray | None = None
    pet_id: int | None = None
    pet_name: str | None = None


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

    # Weight factors for multi-signal matching
    WEIGHT_EMBEDDING = 0.5
    WEIGHT_COLOR = 0.3
    WEIGHT_BREED = 0.1
    WEIGHT_TEMPORAL = 0.1

    def __init__(
        self,
        db: Database,
        model_name: str = DEFAULT_MODEL,
        use_gpu: bool = True,
        confidence_threshold: float = 0.5,
        pets_only_mode: bool = True,
    ):
        """Initialize pet analyzer.

        Args:
            db: Database instance
            model_name: YOLO model name
            use_gpu: Whether to use GPU acceleration
            confidence_threshold: Minimum detection confidence
            pets_only_mode: Only detect common pets (dog, cat, bird), not wild animals
        """
        self.db = db
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold
        self.pets_only_mode = pets_only_mode

        self._model: YOLO | None = None
        self._model_loaded = False

        # CLIP model for embeddings and breed classification
        self._clip_model = None
        self._clip_preprocess = None
        self._clip_tokenizer = None
        self._clip_device = None
        self._clip_loaded = False
        self._breed_embeddings: dict[str, dict[str, object]] = {}

        # Progress tracking
        self.progress = PetAnalysisProgress()
        self._cancel_event = Event()
        self._progress_callback: Callable[[PetAnalysisProgress], None] | None = None

        # Cache for pet data
        self._pet_histograms: dict[int, np.ndarray] = {}
        self._pet_embeddings: dict[int, np.ndarray] = {}

    def set_progress_callback(
        self, callback: Callable[[PetAnalysisProgress], None] | None
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
        self._clip_model = None
        self._clip_preprocess = None
        self._clip_tokenizer = None
        self._clip_loaded = False
        self._breed_embeddings.clear()
        logger.info("Pet detection model unloaded")

    # ==========================================================================
    # CLIP Visual Embeddings & Breed Classification
    # ==========================================================================

    def load_clip_model(self) -> bool:
        """Load CLIP model for visual embeddings and breed classification."""
        if not CLIP_AVAILABLE:
            logger.debug("CLIP not available for pet embeddings")
            return False

        if self._clip_loaded:
            return True

        try:
            config = get_config()
            torch_home = os.path.join(
                config.ai.models_directory or os.path.join(
                    os.path.expanduser("~"), ".duplicleaner", "models"
                ),
                "torch",
            )
            os.environ.setdefault("TORCH_HOME", torch_home)

            model_name = config.ai.scene_model or "ViT-L-14"
            self._clip_device = "cuda" if self.use_gpu and torch.cuda.is_available() else "cpu"

            self._clip_model, _, self._clip_preprocess = open_clip.create_model_and_transforms(
                model_name, pretrained="openai", device=self._clip_device,
            )
            self._clip_tokenizer = open_clip.get_tokenizer(model_name)
            self._clip_model.eval()
            self._clip_loaded = True

            # Pre-compute breed text embeddings for zero-shot classification
            self._compute_breed_embeddings()

            logger.info("CLIP model loaded for pet embeddings (%s)", self._clip_device)
            return True

        except Exception as e:
            logger.warning("Failed to load CLIP for pet embeddings: %s", e)
            self._clip_loaded = False
            return False

    def _compute_breed_embeddings(self) -> None:
        """Pre-compute text embeddings for breed labels."""
        if not self._clip_loaded:
            return

        self._breed_embeddings.clear()

        breed_lists = {
            "dog": DOG_BREEDS,
            "cat": CAT_BREEDS,
            "bird": BIRD_BREEDS,
        }

        for species, breeds in breed_lists.items():
            prompts = [f"a photo of a {breed}" for breed in breeds]
            tokens = self._clip_tokenizer(prompts).to(self._clip_device)

            with torch.no_grad():
                text_features = self._clip_model.encode_text(tokens)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            self._breed_embeddings[species] = {
                "labels": breeds,
                "embeddings": text_features,
            }

        logger.debug("Pre-computed breed embeddings for %d species", len(self._breed_embeddings))

    def extract_visual_embedding(self, image_region: np.ndarray) -> np.ndarray | None:
        """Extract CLIP visual embedding from a pet image region.

        Args:
            image_region: BGR image array of the pet crop

        Returns:
            L2-normalized embedding vector or None
        """
        if not self._clip_loaded and not self.load_clip_model():
            return None

        if not PIL_AVAILABLE:
            return None

        try:
            # Convert BGR to RGB PIL image
            rgb = cv2.cvtColor(image_region, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)

            image_input = self._clip_preprocess(pil_image).unsqueeze(0).to(self._clip_device)

            with torch.no_grad():
                embedding = self._clip_model.encode_image(image_input)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            return embedding.cpu().numpy().flatten()

        except Exception as e:
            logger.warning("Failed to extract pet visual embedding: %s", e)
            return None

    def classify_breed(self, image_region: np.ndarray, species: str) -> tuple[str | None, float]:
        """Classify pet breed using CLIP zero-shot classification.

        Args:
            image_region: BGR image array of the pet crop
            species: Detected species (dog, cat, bird)

        Returns:
            Tuple of (breed_name, confidence) or (None, 0.0)
        """
        if not self._clip_loaded and not self.load_clip_model():
            return None, 0.0

        if species not in self._breed_embeddings:
            return None, 0.0

        if not PIL_AVAILABLE:
            return None, 0.0

        try:
            # Get image embedding
            rgb = cv2.cvtColor(image_region, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)
            image_input = self._clip_preprocess(pil_image).unsqueeze(0).to(self._clip_device)

            with torch.no_grad():
                image_features = self._clip_model.encode_image(image_input)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Compare against breed text embeddings
            breed_data = self._breed_embeddings[species]
            text_features = breed_data["embeddings"]
            labels = breed_data["labels"]

            similarities = (image_features @ text_features.T).squeeze(0)
            probs = torch.softmax(similarities * 100, dim=-1)

            best_idx = int(probs.argmax())
            best_conf = float(probs[best_idx])

            if best_conf >= 0.05:  # Minimum threshold for breed assignment
                return labels[best_idx], best_conf

            return None, 0.0

        except Exception as e:
            logger.warning("Breed classification failed: %s", e)
            return None, 0.0

    def analyze_dominant_colors(self, image_region: np.ndarray) -> list[str]:
        """Analyze dominant colors/markings of a pet using CLIP.

        Args:
            image_region: BGR image array of the pet crop

        Returns:
            List of matching color descriptions
        """
        if not self._clip_loaded and not self.load_clip_model():
            return []

        if not PIL_AVAILABLE:
            return []

        try:
            rgb = cv2.cvtColor(image_region, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)
            image_input = self._clip_preprocess(pil_image).unsqueeze(0).to(self._clip_device)

            prompts = [f"a {color} colored pet" for color in PET_COLOR_LABELS]
            tokens = self._clip_tokenizer(prompts).to(self._clip_device)

            with torch.no_grad():
                image_features = self._clip_model.encode_image(image_input)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = self._clip_model.encode_text(tokens)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            similarities = (image_features @ text_features.T).squeeze(0)
            probs = torch.softmax(similarities * 100, dim=-1)

            # Return colors with probability > 10%
            colors = []
            for idx, prob in enumerate(probs):
                if float(prob) > 0.10:
                    colors.append(PET_COLOR_LABELS[idx])

            return colors[:3]  # Top 3 at most

        except Exception as e:
            logger.warning("Color analysis failed: %s", e)
            return []

    def _serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Serialize a numpy embedding to bytes."""
        return embedding.astype(np.float32).tobytes()

    def _deserialize_embedding(self, data: bytes) -> np.ndarray:
        """Deserialize bytes back to numpy embedding."""
        return np.frombuffer(data, dtype=np.float32)

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
        if not self._model_loaded and not self.load_model():
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

            # Choose class list based on pets_only_mode
            class_list = COMMON_PETS_ONLY if self.pets_only_mode else ANIMAL_CLASSES

            detected = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get class
                    cls_id = int(box.cls[0])
                    if cls_id not in class_list:
                        continue

                    species = class_list[cls_id]
                    confidence = float(box.conf[0])

                    if confidence < self.confidence_threshold:
                        continue

                    # Get bounding box
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    x, y = int(x1), int(y1)
                    w, h = int(x2 - x1), int(y2 - y1)

                    # Extract region for analysis
                    pet_region = img[y:y+h, x:x+w]
                    if pet_region.size == 0:
                        continue

                    color_hist = self._compute_color_histogram(pet_region)

                    # Extract visual embedding via CLIP
                    visual_emb = self.extract_visual_embedding(pet_region)

                    # Classify breed via CLIP zero-shot
                    breed, breed_conf = self.classify_breed(pet_region, species)

                    # Analyze dominant colors
                    dominant_colors = self.analyze_dominant_colors(pet_region)

                    detected.append(DetectedPet(
                        bbox=(x, y, w, h),
                        species=species,
                        confidence=confidence,
                        breed=breed,
                        breed_confidence=breed_conf,
                        color_histogram=color_hist,
                        visual_embedding=visual_emb,
                        dominant_colors=dominant_colors,
                    ))

            return detected

        except Exception as e:
            logger.error(f"Error detecting pets in {image_path}: {e}")
            return []

    def _compute_color_histogram(self, image: np.ndarray) -> np.ndarray | None:
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
                embedding=self._serialize_embedding(det.visual_embedding) if det.visual_embedding is not None else None,
                estimated_age_stage=age_stage,
            )

            # Store in database
            det_id = self.db.add_pet_detection(detection)
            detection.id = det_id
            detections.append(detection)

        return detections

    def _estimate_age_stage(self, detected: DetectedPet) -> PetAgeStage | None:
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

    def load_pet_data(self) -> None:
        """Load all pet histograms and embeddings into cache."""
        self._pet_histograms.clear()
        self._pet_embeddings.clear()

        pets = self.db.get_all_pets()
        for pet in pets:
            if pet.id is None:
                continue

            detections = self.db.get_pet_detections_for_pet(pet.id)

            histograms = []
            embeddings = []
            for det in detections:
                if det.color_histogram:
                    hist = self._deserialize_histogram(det.color_histogram)
                    histograms.append(hist)
                if det.embedding:
                    emb = self._deserialize_embedding(det.embedding)
                    embeddings.append(emb)

            if histograms:
                self._pet_histograms[pet.id] = np.mean(histograms, axis=0)
            if embeddings:
                avg_emb = np.mean(embeddings, axis=0)
                avg_emb = avg_emb / np.linalg.norm(avg_emb)
                self._pet_embeddings[pet.id] = avg_emb

    def load_pet_histograms(self) -> None:
        """Load all pet color histograms into cache (legacy alias)."""
        self.load_pet_data()

    def _compute_temporal_score(
        self, detection: PetDetection, pet_id: int
    ) -> float:
        """Compute temporal proximity score between detection and pet's photos.

        Photos close in time to existing pet photos score higher, enabling
        temporal bridging across life stages.

        Returns:
            Score between 0.0 and 1.0
        """
        file_record = self.db.get_file(detection.file_id)
        if not file_record or not file_record.modified:
            return 0.0

        det_date = file_record.modified
        pet_detections = self.db.get_pet_detections_for_pet(pet_id)

        if not pet_detections:
            return 0.0

        # Find closest pet photo by date
        min_days = float("inf")
        for pd in pet_detections:
            pf = self.db.get_file(pd.file_id)
            if pf and pf.modified:
                days_diff = abs((det_date - pf.modified).days)
                if days_diff < min_days:
                    min_days = days_diff

        if min_days == float("inf"):
            return 0.0

        # Score: 1.0 for same day, decays over time
        # Within 30 days: high score (0.8-1.0)
        # Within 1 year: moderate (0.4-0.8)
        # Beyond 2 years: low (<0.3)
        if min_days <= 1:
            return 1.0
        elif min_days <= 30:
            return 0.8 + 0.2 * (1 - min_days / 30)
        elif min_days <= 365:
            return 0.4 + 0.4 * (1 - min_days / 365)
        elif min_days <= 730:
            return 0.1 + 0.3 * (1 - min_days / 730)
        else:
            return max(0.0, 0.1 * (1 - min_days / 3650))

    def match_detection(
        self,
        detection: PetDetection,
        threshold: float = MATCH_THRESHOLD_MEDIUM,
    ) -> PetMatch | None:
        """Match a detection to a known pet using multi-signal scoring.

        Combines visual embedding similarity, color histogram correlation,
        breed matching, and temporal proximity for robust matching.

        Args:
            detection: Detection to match
            threshold: Minimum similarity threshold

        Returns:
            PetMatch if found, None otherwise
        """
        has_hist = detection.color_histogram is not None
        has_emb = detection.embedding is not None

        if not has_hist and not has_emb:
            return None

        if not self._pet_histograms and not self._pet_embeddings:
            self.load_pet_data()

        det_hist = self._deserialize_histogram(detection.color_histogram) if has_hist else None
        det_emb = self._deserialize_embedding(detection.embedding) if has_emb else None
        if det_emb is not None:
            det_emb = det_emb / np.linalg.norm(det_emb)

        best_match: PetMatch | None = None
        best_score = threshold

        # Get all pets to check species and breed
        all_pets = {p.id: p for p in self.db.get_all_pets() if p.id is not None}

        for pet_id in set(list(self._pet_histograms.keys()) + list(self._pet_embeddings.keys())):
            pet = all_pets.get(pet_id)
            if not pet:
                continue

            if pet.species and pet.species != detection.species:
                continue

            # Embedding similarity
            emb_score = 0.0
            if det_emb is not None and pet_id in self._pet_embeddings:
                pet_emb = self._pet_embeddings[pet_id]
                emb_score = float(np.dot(det_emb, pet_emb))
                emb_score = max(0.0, emb_score)

            # Color histogram similarity
            color_score = 0.0
            if det_hist is not None and pet_id in self._pet_histograms:
                color_score = self.compare_histograms(det_hist, self._pet_histograms[pet_id])

            # Breed match bonus
            breed_score = 0.0
            if detection.breed and pet.breed:
                if detection.breed.lower() == pet.breed.lower():
                    breed_score = 1.0

            # Temporal proximity
            temporal_score = self._compute_temporal_score(detection, pet_id)

            # Weighted combination
            if has_emb and emb_score > 0:
                score = (
                    self.WEIGHT_EMBEDDING * emb_score
                    + self.WEIGHT_COLOR * color_score
                    + self.WEIGHT_BREED * breed_score
                    + self.WEIGHT_TEMPORAL * temporal_score
                )
            else:
                # Fallback to color-only when no embeddings
                score = (
                    0.7 * color_score
                    + 0.15 * breed_score
                    + 0.15 * temporal_score
                )

            if score > best_score:
                best_score = score
                best_match = PetMatch(
                    pet_id=pet_id,
                    pet_name=pet.name,
                    similarity=score,
                    color_match=color_score,
                    embedding_match=emb_score,
                    breed_match=breed_score,
                    temporal_score=temporal_score,
                )

        return best_match

    def match_and_assign_detections(
        self,
        detections: list[PetDetection] | None = None,
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
        threshold: float = MATCH_THRESHOLD_MEDIUM,
        auto_assign: bool = True,
    ) -> tuple[int, int]:
        """Find and assign unassigned detections that match a specific pet.

        Uses multi-signal matching (embedding + color + breed + temporal).

        Args:
            pet_id: ID of the pet to find more detections for
            threshold: Minimum similarity threshold
            auto_assign: Whether to automatically assign matching detections

        Returns:
            Tuple of (matches_found, detections_assigned)
        """
        pet = self.db.get_pet(pet_id)
        if not pet:
            logger.warning("Pet %d not found", pet_id)
            return 0, 0

        self.load_pet_data()

        has_data = pet_id in self._pet_histograms or pet_id in self._pet_embeddings
        if not has_data:
            logger.warning("No matching data found for pet %d", pet_id)
            return 0, 0

        pet_hist = self._pet_histograms.get(pet_id)
        pet_emb = self._pet_embeddings.get(pet_id)

        detections = self.db.get_unassigned_pet_detections()

        self.progress.phase = "matching"
        self._notify_progress()

        matches_found = 0
        assigned = 0

        for detection in detections:
            if self._cancel_event.is_set():
                break

            if pet.species and pet.species != detection.species:
                continue

            # Embedding similarity
            emb_score = 0.0
            if pet_emb is not None and detection.embedding:
                det_emb = self._deserialize_embedding(detection.embedding)
                det_emb = det_emb / np.linalg.norm(det_emb)
                emb_score = max(0.0, float(np.dot(det_emb, pet_emb)))

            # Color similarity
            color_score = 0.0
            if pet_hist is not None and detection.color_histogram:
                det_hist = self._deserialize_histogram(detection.color_histogram)
                color_score = self.compare_histograms(det_hist, pet_hist)

            # Breed match
            breed_score = 0.0
            if detection.breed and pet.breed and detection.breed.lower() == pet.breed.lower():
                breed_score = 1.0

            # Temporal proximity
            temporal_score = self._compute_temporal_score(detection, pet_id)

            # Weighted score
            if pet_emb is not None and emb_score > 0:
                score = (
                    self.WEIGHT_EMBEDDING * emb_score
                    + self.WEIGHT_COLOR * color_score
                    + self.WEIGHT_BREED * breed_score
                    + self.WEIGHT_TEMPORAL * temporal_score
                )
            else:
                score = 0.7 * color_score + 0.15 * breed_score + 0.15 * temporal_score

            if score >= threshold:
                matches_found += 1
                if auto_assign:
                    self.db.assign_pet_detection_to_pet(detection.id, pet_id)
                    assigned += 1
                    self.db.update_pet_photo_count(pet_id)

        self.progress.pets_matched = assigned
        self._notify_progress()

        logger.info(
            "Found %d matches for pet %d (%s), assigned %d",
            matches_found, pet_id, pet.name, assigned,
        )
        return matches_found, assigned

    # ==========================================================================
    # Pet Clustering
    # ==========================================================================

    def _compute_pairwise_distance(
        self, det_a: PetDetection, det_b: PetDetection,
        hist_a: np.ndarray | None, hist_b: np.ndarray | None,
    ) -> float:
        """Compute distance between two detections using available signals."""
        scores = []
        weights = []

        # Embedding similarity (primary signal when available)
        if det_a.embedding and det_b.embedding:
            emb_a = self._deserialize_embedding(det_a.embedding)
            emb_b = self._deserialize_embedding(det_b.embedding)
            emb_a = emb_a / np.linalg.norm(emb_a)
            emb_b = emb_b / np.linalg.norm(emb_b)
            emb_sim = max(0.0, float(np.dot(emb_a, emb_b)))
            scores.append(emb_sim)
            weights.append(0.6)

        # Color histogram similarity
        if hist_a is not None and hist_b is not None:
            color_sim = self.compare_histograms(hist_a, hist_b)
            scores.append(color_sim)
            weights.append(0.3 if det_a.embedding else 0.8)

        # Breed match bonus
        if det_a.breed and det_b.breed:
            breed_sim = 1.0 if det_a.breed.lower() == det_b.breed.lower() else 0.0
            scores.append(breed_sim)
            weights.append(0.1)

        if not scores:
            return 1.0  # Maximum distance if no signals

        total_weight = sum(weights)
        similarity = sum(s * w for s, w in zip(scores, weights)) / total_weight
        return 1.0 - similarity

    def cluster_detections(
        self,
        species: str | None = None,
        eps: float = DBSCAN_EPS,
        min_samples: int = DBSCAN_MIN_SAMPLES,
    ) -> list[PetCluster]:
        """Cluster unassigned pet detections using multi-signal distance.

        Combines visual embeddings, color histograms, and breed info.

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

        detections = self.db.get_unassigned_pet_detections()

        if species:
            detections = [d for d in detections if d.species == species]

        if len(detections) == 0:
            return []

        self.progress.phase = "clustering"
        self._notify_progress()

        # Group by species
        by_species: dict[str, list[PetDetection]] = {}
        for det in detections:
            if det.species not in by_species:
                by_species[det.species] = []
            by_species[det.species].append(det)

        clusters = []
        cluster_id = 0

        for species_name, species_detections in by_species.items():
            if len(species_detections) < min_samples:
                for det in species_detections:
                    if det.id is None:
                        continue
                    hist = None
                    if det.color_histogram:
                        hist = self._deserialize_histogram(det.color_histogram)
                    cluster = PetCluster(
                        cluster_id=cluster_id,
                        detection_ids=[det.id],
                        sample_detections=[det],
                        species=species_name,
                        avg_color_histogram=hist,
                    )
                    clusters.append(cluster)
                    cluster_id += 1
                continue

            # Filter detections that have at least one matching signal
            valid_detections = []
            valid_hists = []
            for det in species_detections:
                has_signal = det.color_histogram is not None or det.embedding is not None
                if has_signal:
                    hist = self._deserialize_histogram(det.color_histogram) if det.color_histogram else None
                    valid_detections.append(det)
                    valid_hists.append(hist)

            if len(valid_detections) < min_samples:
                continue

            # Compute multi-signal distance matrix
            n = len(valid_detections)
            distance_matrix = np.zeros((n, n))

            for i in range(n):
                for j in range(i + 1, n):
                    dist = self._compute_pairwise_distance(
                        valid_detections[i], valid_detections[j],
                        valid_hists[i], valid_hists[j],
                    )
                    distance_matrix[i, j] = dist
                    distance_matrix[j, i] = dist

            clustering = DBSCAN(
                eps=eps,
                min_samples=min_samples,
                metric="precomputed",
            ).fit(distance_matrix)

            labels = clustering.labels_
            unique_labels = set(labels)
            unique_labels.discard(-1)

            for label in unique_labels:
                indices = np.where(labels == label)[0]
                cluster_dets = [valid_detections[i] for i in indices]
                cluster_hists = [h for i, h in enumerate(valid_hists) if i in indices and h is not None]

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

        logger.info("Created %d pet clusters (including singletons)", len(clusters))
        return clusters

    # ==========================================================================
    # Pet Management
    # ==========================================================================

    def create_pet_from_cluster(
        self,
        cluster: PetCluster,
        name: str,
        breed: str | None = None,
        birth_year: int | None = None,
        color_pattern: str | None = None,
    ) -> int | None:
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
        self.load_pet_data()

        logger.info(
            "Created pet '%s' (%s) with %d photos",
            name, cluster.species, len(cluster.detection_ids),
        )
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

        by_year: dict[int, list[PetDetection]] = {}
        for det in detections:
            file_record = self.db.get_file(det.file_id)
            if file_record and file_record.modified:
                year = file_record.modified.year
                if year not in by_year:
                    by_year[year] = []
                by_year[year].append(det)

        return sorted(by_year.items())

    # ==========================================================================
    # Temporal Bridging
    # ==========================================================================

    def bridge_temporal_gaps(
        self,
        pet_id: int,
        max_gap_years: int = 3,
        threshold: float = MATCH_THRESHOLD_LOW,
    ) -> tuple[int, int]:
        """Bridge temporal gaps in a pet's timeline by finding intermediate detections.

        Searches for unassigned detections that fall in timeline gaps and
        match the pet with relaxed thresholds based on temporal proximity.

        Args:
            pet_id: Pet to bridge gaps for
            max_gap_years: Maximum gap in years to try bridging
            threshold: Lowered similarity threshold for gap bridging

        Returns:
            Tuple of (gaps_found, detections_assigned)
        """
        pet = self.db.get_pet(pet_id)
        if not pet:
            return 0, 0

        timeline = self.get_pet_timeline(pet_id)
        if len(timeline) < 2:
            return 0, 0

        self.load_pet_data()

        # Identify gaps
        years = [year for year, _ in timeline]
        gaps = []
        for i in range(len(years) - 1):
            gap = years[i + 1] - years[i]
            if gap >= 2 and gap <= max_gap_years:
                gaps.append((years[i], years[i + 1]))

        if not gaps:
            return 0, 0

        # Get unassigned detections
        unassigned = self.db.get_unassigned_pet_detections()
        gap_dets = []
        for det in unassigned:
            if pet.species and pet.species != det.species:
                continue
            file_rec = self.db.get_file(det.file_id)
            if file_rec and file_rec.modified:
                for gap_start, gap_end in gaps:
                    if gap_start < file_rec.modified.year < gap_end:
                        gap_dets.append(det)
                        break

        if not gap_dets:
            return len(gaps), 0

        # Try matching with relaxed threshold
        assigned = 0
        for det in gap_dets:
            match = self.match_detection(det, threshold=threshold)
            if match and match.pet_id == pet_id:
                self.db.assign_pet_detection_to_pet(det.id, pet_id)
                assigned += 1

        if assigned > 0:
            self.db.update_pet_photo_count(pet_id)
            self.load_pet_data()

        logger.info(
            "Temporal bridging for pet %d (%s): %d gaps, %d detections assigned",
            pet_id, pet.name, len(gaps), assigned,
        )
        return len(gaps), assigned

    def get_life_stage_summary(self, pet_id: int) -> dict[str, int]:
        """Get count of detections per life stage for a pet.

        Returns:
            Dict mapping stage name to count
        """
        detections = self.db.get_pet_detections_for_pet(pet_id)
        stages: dict[str, int] = {}
        for det in detections:
            stage = det.estimated_age_stage.value if det.estimated_age_stage else "unknown"
            stages[stage] = stages.get(stage, 0) + 1
        return stages

    def cancel(self) -> None:
        """Cancel ongoing operation."""
        self._cancel_event.set()
        logger.info("Pet analysis cancelled")
