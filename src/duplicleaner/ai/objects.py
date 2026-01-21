"""Object detection module.

Uses YOLOv8 for detecting objects in images and generating tags.
"""

import os
from dataclasses import dataclass
from threading import Event
from typing import Callable, Optional

from ..db.database import Database
from ..db.models import FileRecord
from ..utils.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import YOLO
YOLO_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    logger.warning("Ultralytics YOLO not available. Object detection disabled.")


# COCO class names (80 classes)
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush"
]


@dataclass
class DetectedObject:
    """A detected object in an image."""
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, width, height


@dataclass
class ObjectDetectionResult:
    """Result of object detection for an image."""
    file_id: int
    objects: list[DetectedObject]
    unique_labels: list[str]  # Deduplicated object names


@dataclass
class ObjectDetectionProgress:
    """Progress tracking for object detection."""
    total_files: int = 0
    processed_files: int = 0
    objects_detected: int = 0
    current_file: str = ""
    phase: str = "initializing"
    is_cancelled: bool = False

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class ObjectDetector:
    """Object detection using YOLOv8."""

    # Model options
    DEFAULT_MODEL = "yolov8n.pt"  # nano - fast
    LARGE_MODEL = "yolov8l.pt"   # large - more accurate

    def __init__(
        self,
        db: Database,
        model_name: str = DEFAULT_MODEL,
        use_gpu: bool = True,
        confidence_threshold: float = 0.5,
    ):
        """Initialize object detector.

        Args:
            db: Database instance
            model_name: YOLO model name
            use_gpu: Whether to use GPU
            confidence_threshold: Minimum detection confidence
        """
        self.db = db
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold

        self._model: Optional["YOLO"] = None
        self._model_loaded = False

        # Progress tracking
        self.progress = ObjectDetectionProgress()
        self._cancel_event = Event()
        self._progress_callback: Optional[Callable[[ObjectDetectionProgress], None]] = None

    def set_progress_callback(
        self, callback: Optional[Callable[[ObjectDetectionProgress], None]]
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
        """Check if YOLO is available."""
        return YOLO_AVAILABLE

    def load_model(self) -> bool:
        """Load the YOLO model.

        Returns:
            True if loaded successfully
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

            # Load model
            model_path = os.path.join(model_dir, self.model_name)
            self._model = YOLO(model_path if os.path.exists(model_path) else self.model_name)

            # Set device
            device = "cuda" if self.use_gpu else "cpu"
            self._model.to(device)

            self._model_loaded = True
            logger.info(f"YOLO model loaded: {self.model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self._model = None
            self._model_loaded = False
            return False

    def unload_model(self) -> None:
        """Unload model to free memory."""
        self._model = None
        self._model_loaded = False
        logger.info("YOLO model unloaded")

    def detect_objects(self, image_path: str) -> Optional[ObjectDetectionResult]:
        """Detect objects in an image.

        Args:
            image_path: Path to image file

        Returns:
            ObjectDetectionResult or None on error
        """
        if not self._model_loaded:
            if not self.load_model():
                return None

        try:
            # Run detection
            results = self._model(image_path, verbose=False)

            detected_objects = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get class
                    cls_id = int(box.cls[0])
                    class_name = COCO_CLASSES[cls_id] if cls_id < len(COCO_CLASSES) else f"class_{cls_id}"

                    # Get confidence
                    confidence = float(box.conf[0])
                    if confidence < self.confidence_threshold:
                        continue

                    # Get bounding box
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    bbox = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))

                    detected_objects.append(DetectedObject(
                        class_name=class_name,
                        confidence=confidence,
                        bbox=bbox,
                    ))

            # Get unique labels
            unique_labels = list(set(obj.class_name for obj in detected_objects))

            return ObjectDetectionResult(
                file_id=0,  # Will be set by caller
                objects=detected_objects,
                unique_labels=unique_labels,
            )

        except Exception as e:
            logger.error(f"Error detecting objects in {image_path}: {e}")
            return None

    def analyze_file(self, file_record: FileRecord) -> Optional[list[str]]:
        """Analyze a file and store detected objects.

        Args:
            file_record: FileRecord to analyze

        Returns:
            List of detected object names or None
        """
        if file_record.id is None:
            return None

        result = self.detect_objects(file_record.path)
        if not result:
            return None

        # Update database
        self.db.update_scene_objects(file_record.id, result.unique_labels)

        return result.unique_labels

    def analyze_batch(
        self,
        file_records: list[FileRecord],
        skip_existing: bool = True,
    ) -> int:
        """Analyze a batch of files.

        Args:
            file_records: Files to analyze
            skip_existing: Skip files with existing object data

        Returns:
            Number of files analyzed
        """
        self.progress = ObjectDetectionProgress(
            total_files=len(file_records),
            phase="detecting",
        )
        self._cancel_event.clear()
        self._notify_progress()

        analyzed = 0
        total_objects = 0

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
                if existing and existing.objects:
                    continue

            # Analyze
            labels = self.analyze_file(file_record)
            if labels:
                analyzed += 1
                total_objects += len(labels)
                self.progress.objects_detected = total_objects

        self.progress.phase = "complete"
        self._notify_progress()

        return analyzed

    def get_files_with_object(self, object_name: str) -> list[int]:
        """Find all files containing a specific object.

        Args:
            object_name: Object name to search for

        Returns:
            List of file IDs
        """
        # This would need a more efficient implementation with object tags table
        # For now, search through scene analyses
        analyses = self.db.get_all_scene_analyses_with_embeddings()
        results = []

        import json
        for file_id, _, _ in analyses:
            analysis = self.db.get_scene_analysis(file_id)
            if analysis and analysis.objects:
                objects = json.loads(analysis.objects)
                if object_name.lower() in [o.lower() for o in objects]:
                    results.append(file_id)

        return results

    def cancel(self) -> None:
        """Cancel ongoing operation."""
        self._cancel_event.set()
        logger.info("Object detection cancelled")
