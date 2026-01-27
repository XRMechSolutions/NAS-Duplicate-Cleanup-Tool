"""Face detection and recognition module.

Uses InsightFace (buffalo_l model) for face detection, embedding extraction,
and recognition. Includes temporal bridging for age progression tracking.
"""

import os
from pathlib import Path
import struct
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Event
from typing import Callable, Optional

import numpy as np

from ..db.database import Database
from ..db.models import Face, Person, FileRecord
from ..utils.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import AI libraries
INSIGHTFACE_AVAILABLE = False
SKLEARN_AVAILABLE = False

try:
    # Suppress FutureWarning from scikit-image's deprecated estimate method
    # used internally by insightface. The warning fires at runtime during
    # face alignment. This will be fixed when insightface updates to use
    # SimilarityTransform.from_estimate() instead of tform.estimate().
    warnings.filterwarnings(
        "ignore",
        message=r".*`estimate` is deprecated.*",
        category=FutureWarning,
    )
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    logger.warning("InsightFace not available. Face recognition disabled.")

try:
    from sklearn.cluster import DBSCAN
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning("scikit-learn not available. Face clustering disabled.")


class AgeStage(Enum):
    """Life stage for age-based embedding storage."""
    BABY = "baby"          # 0-2 years
    TODDLER = "toddler"    # 2-5 years
    CHILD = "child"        # 5-12 years
    TEEN = "teen"          # 13-17 years
    ADULT = "adult"        # 18+ years

    @classmethod
    def from_age(cls, age: int) -> "AgeStage":
        """Get age stage from age in years."""
        if age < 2:
            return cls.BABY
        elif age < 5:
            return cls.TODDLER
        elif age < 12:
            return cls.CHILD
        elif age < 18:
            return cls.TEEN
        else:
            return cls.ADULT


@dataclass
class DetectedFace:
    """A face detected in an image."""
    bbox: tuple[int, int, int, int]  # x, y, width, height
    embedding: np.ndarray            # 512-dim vector
    confidence: float
    estimated_age: Optional[int] = None
    estimated_gender: Optional[str] = None
    landmarks: Optional[np.ndarray] = None


@dataclass
class FaceMatch:
    """Result of matching a face to a known person."""
    person_id: int
    person_name: Optional[str]
    similarity: float
    age_stage: Optional[AgeStage] = None


@dataclass
class FaceCluster:
    """A cluster of similar faces (potential person)."""
    cluster_id: int
    face_ids: list[int]
    sample_faces: list[Face]  # Representative faces
    avg_embedding: Optional[np.ndarray] = None
    person_id: Optional[int] = None  # If assigned
    person_name: Optional[str] = None


@dataclass
class FaceAnalysisProgress:
    """Progress tracking for face analysis."""
    total_files: int = 0
    processed_files: int = 0
    faces_detected: int = 0
    faces_matched: int = 0
    current_file: str = ""
    phase: str = "initializing"
    is_cancelled: bool = False

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class FaceAnalyzer:
    """Face detection, recognition, and clustering engine."""

    # Embedding dimensions
    EMBEDDING_DIM = 512

    # Similarity thresholds
    MATCH_THRESHOLD_HIGH = 0.9    # Very likely same person
    MATCH_THRESHOLD_MEDIUM = 0.7  # Possible match, needs review
    MATCH_THRESHOLD_LOW = 0.5     # Unlikely match

    # Temporal bridging thresholds (lower for closer dates)
    TEMPORAL_THRESHOLD_SAME_DAY = 0.5
    TEMPORAL_THRESHOLD_SAME_MONTH = 0.6
    TEMPORAL_THRESHOLD_SAME_YEAR = 0.7
    TEMPORAL_THRESHOLD_DIFFERENT_YEARS = 0.8

    # DBSCAN clustering parameters
    DBSCAN_EPS = 0.5
    DBSCAN_MIN_SAMPLES = 3

    def __init__(
        self,
        db: Database,
        model_name: str = "buffalo_l",
        use_gpu: bool = True,
        det_size: tuple[int, int] = (640, 640),
    ):
        """Initialize face analyzer.

        Args:
            db: Database instance
            model_name: InsightFace model name (buffalo_l, buffalo_s, etc.)
            use_gpu: Whether to use GPU acceleration
            det_size: Detection input size
        """
        self.db = db
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.det_size = det_size
        config = get_config()
        self.det_conf_threshold = config.ai.face_detection_threshold
        self.match_threshold = config.ai.face_recognition_threshold
        self.cluster_similarity_threshold = config.ai.face_clustering_threshold

        self._model: Optional["FaceAnalysis"] = None
        self._model_loaded = False

        # Progress tracking
        self.progress = FaceAnalysisProgress()
        self._cancel_event = Event()
        self._progress_callback: Optional[Callable[[FaceAnalysisProgress], None]] = None

        # Cache for person embeddings
        self._person_embeddings: dict[int, list[tuple[AgeStage, np.ndarray]]] = {}

    def set_progress_callback(
        self, callback: Optional[Callable[[FaceAnalysisProgress], None]]
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
        """Check if face recognition is available."""
        return INSIGHTFACE_AVAILABLE and SKLEARN_AVAILABLE

    def load_model(self) -> bool:
        """Load the face analysis model.

        Returns:
            True if model loaded successfully
        """
        if not INSIGHTFACE_AVAILABLE:
            logger.error("InsightFace not installed")
            return False

        if self._model_loaded:
            return True

        try:
            self.progress.phase = "loading_model"
            self._notify_progress()

            # Determine providers
            use_gpu = self.use_gpu and self._cuda_available()
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_gpu else ["CPUExecutionProvider"]

            # Get model directory
            config = get_config()
            model_dir = config.ai.models_directory
            if not model_dir:
                model_dir = os.path.join(os.path.expanduser("~"), ".duplicleaner", "models")

            os.makedirs(model_dir, exist_ok=True)

            # Initialize FaceAnalysis
            self._model = FaceAnalysis(
                name=self.model_name,
                root=model_dir,
                providers=providers,
            )
            self._model.prepare(ctx_id=0 if use_gpu else -1, det_size=self.det_size)

            self._model_loaded = True
            logger.info(f"Loaded face model: {self.model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load face model: {e}")
            self._model = None
            self._model_loaded = False
            return False

    def unload_model(self) -> None:
        """Unload the model to free memory."""
        self._model = None
        self._model_loaded = False
        logger.info("Face model unloaded")

    def _cuda_available(self) -> bool:
        """Check whether CUDA can be used by InsightFace/onnxruntime."""
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if "CUDAExecutionProvider" not in providers:
                return False
            if os.name == "nt":
                import ctypes
                capi_dir = Path(ort.__file__).resolve().parent / "capi"
                provider_dll = capi_dir / "onnxruntime_providers_cuda.dll"
                if provider_dll.exists():
                    try:
                        ctypes.WinDLL(str(provider_dll))
                    except OSError:
                        return False
        except ImportError:
            return False

        return True

    # ==========================================================================
    # Face Detection
    # ==========================================================================

    def detect_faces(self, image_path: str) -> list[DetectedFace]:
        """Detect faces in an image.

        Args:
            image_path: Path to image file

        Returns:
            List of detected faces with embeddings
        """
        if not self._model_loaded:
            if not self.load_model():
                return []

        try:
            import cv2
            img = cv2.imread(image_path)
            if img is None:
                try:
                    from PIL import Image, ImageOps
                    with Image.open(image_path) as pil_img:
                        pil_img = ImageOps.exif_transpose(pil_img)
                        pil_img = pil_img.convert("RGB")
                        img = np.array(pil_img)[:, :, ::-1]
                except Exception:
                    logger.warning(f"Could not read image: {image_path}")
                    return []

            # Run face detection
            faces = self._model.get(img)

            detected = []
            for face in faces:
                # Get bounding box (convert from xyxy to xywh)
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                width = x2 - x1
                height = y2 - y1

                # Get embedding
                embedding = face.embedding
                if embedding is None:
                    continue

                # Get confidence
                confidence = float(face.det_score) if hasattr(face, "det_score") else 0.0
                if confidence < self.det_conf_threshold:
                    continue

                # Get age/gender if available
                age = int(face.age) if hasattr(face, "age") and face.age is not None else None
                gender = "M" if hasattr(face, "gender") and face.gender == 1 else "F" if hasattr(face, "gender") and face.gender == 0 else None

                # Get landmarks if available
                landmarks = face.landmark_2d_106 if hasattr(face, "landmark_2d_106") else None

                detected.append(DetectedFace(
                    bbox=(int(x1), int(y1), int(width), int(height)),
                    embedding=embedding,
                    confidence=confidence,
                    estimated_age=age,
                    estimated_gender=gender,
                    landmarks=landmarks,
                ))

            return detected

        except Exception as e:
            logger.error(f"Error detecting faces in {image_path}: {e}")
            return []

    def analyze_file(self, file_record: FileRecord) -> list[Face]:
        """Analyze a file for faces and store results.

        Args:
            file_record: FileRecord to analyze

        Returns:
            List of Face objects stored in database
        """
        if file_record.id is None:
            return []
        if self.db.is_face_blacklisted(file_record.id):
            return []

        # Detect faces
        detected = self.detect_faces(file_record.path)
        if not detected:
            self.db.mark_faces_analyzed(file_record.id, faces_found=0)
            return []

        faces = []
        for det in detected:
            # Create Face object
            face = Face(
                file_id=file_record.id,
                bbox_x=det.bbox[0],
                bbox_y=det.bbox[1],
                bbox_w=det.bbox[2],
                bbox_h=det.bbox[3],
                embedding=self._serialize_embedding(det.embedding),
                confidence=det.confidence,
                estimated_age=det.estimated_age,
                estimated_gender=det.estimated_gender,
            )

            # Store in database
            face_id = self.db.add_face(face)
            face.id = face_id
            faces.append(face)

        self.db.mark_faces_analyzed(file_record.id, faces_found=len(faces))
        return faces

    def analyze_batch(
        self,
        file_records: list[FileRecord],
        skip_existing: bool = True,
    ) -> int:
        """Analyze a batch of files for faces.

        Args:
            file_records: List of files to analyze
            skip_existing: Skip files that already have face data

        Returns:
            Number of faces detected
        """
        self.progress = FaceAnalysisProgress(
            total_files=len(file_records),
            phase="detecting",
        )
        self._cancel_event.clear()
        self._notify_progress()

        total_faces = 0

        for i, file_record in enumerate(file_records):
            if self._cancel_event.is_set():
                self.progress.is_cancelled = True
                break

            self.progress.current_file = file_record.path
            self.progress.processed_files = i + 1
            self._notify_progress()

            # Skip if already analyzed
            if skip_existing and file_record.id:
                existing = self.db.get_faces_for_file(file_record.id)
                if existing or self.db.is_faces_analyzed(file_record.id):
                    continue

            # Analyze
            faces = self.analyze_file(file_record)
            total_faces += len(faces)
            self.progress.faces_detected = total_faces

        self.progress.phase = "complete"
        self._notify_progress()

        return total_faces

    # ==========================================================================
    # Embedding Utilities
    # ==========================================================================

    def _serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Serialize embedding to bytes for database storage."""
        return embedding.astype(np.float32).tobytes()

    def _deserialize_embedding(self, data: bytes) -> np.ndarray:
        """Deserialize embedding from database bytes."""
        return np.frombuffer(data, dtype=np.float32)

    def compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        # Normalize
        emb1_norm = emb1 / np.linalg.norm(emb1)
        emb2_norm = emb2 / np.linalg.norm(emb2)
        # Cosine similarity
        return float(np.dot(emb1_norm, emb2_norm))

    # ==========================================================================
    # Face Clustering
    # ==========================================================================

    def cluster_faces(
        self,
        faces: Optional[list[Face]] = None,
        eps: Optional[float] = None,
        min_samples: int = DBSCAN_MIN_SAMPLES,
        use_known: bool = True,
    ) -> list[FaceCluster]:
        """Cluster unassigned faces into groups.

        Args:
            faces: Faces to cluster (if None, gets unassigned from DB)
            eps: DBSCAN epsilon parameter
            min_samples: Minimum samples for a cluster
            use_known: If True, try to auto-assign faces to known people before clustering

        Returns:
            List of FaceCluster objects
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for clustering")
            return []

        # Get unassigned faces if not provided
        if faces is None:
            if use_known:
                try:
                    _, assigned = self.match_and_assign_faces(
                        faces=None,
                        threshold=self.match_threshold,
                        auto_assign=True,
                    )
                    if assigned:
                        logger.info(f"Auto-assigned {assigned} faces to known people before clustering")
                except Exception as exc:
                    logger.warning(f"Auto-assign before clustering failed: {exc}")
            faces = self.db.get_unassigned_faces(min_confidence=self.det_conf_threshold)

        if len(faces) < min_samples:
            logger.info(f"Not enough faces to cluster: {len(faces)}")
            return []

        self.progress.phase = "clustering"
        self._notify_progress()

        # Extract embeddings
        embeddings = []
        valid_faces = []
        for face in faces:
            if face.embedding:
                emb = self._deserialize_embedding(face.embedding)
                embeddings.append(emb)
                valid_faces.append(face)

        if len(embeddings) < min_samples:
            return []

        # Convert to numpy array
        X = np.array(embeddings, dtype=np.float32)

        # Normalize for cosine distance, skip zero vectors
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        valid_mask = norms.squeeze() > 0
        if not np.all(valid_mask):
            X = X[valid_mask]
            valid_faces = [f for i, f in enumerate(valid_faces) if valid_mask[i]]
            embeddings = [embeddings[i] for i in range(len(embeddings)) if valid_mask[i]]

        if len(X) < min_samples:
            return []

        X_norm = X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-8)

        # Compute distance matrix (1 - similarity)
        similarity_matrix = np.dot(X_norm, X_norm.T)
        similarity_matrix = np.clip(similarity_matrix, -1.0, 1.0)
        distance_matrix = 1.0 - similarity_matrix
        distance_matrix = np.clip(distance_matrix, 0.0, None)
        np.fill_diagonal(distance_matrix, 0.0)

        # Run DBSCAN
        if eps is None:
            eps = max(0.05, min(0.95, 1.0 - self.cluster_similarity_threshold))
        try:
            clustering = DBSCAN(
                eps=eps,
                min_samples=min_samples,
                metric="precomputed",
            ).fit(distance_matrix)
        except ValueError as exc:
            logger.error(f"Face clustering failed: {exc}")
            return []

        # Build clusters
        labels = clustering.labels_
        unique_labels = set(labels)
        unique_labels.discard(-1)  # Remove noise label

        clusters = []
        for label in unique_labels:
            cluster_indices = np.where(labels == label)[0]
            cluster_faces = [valid_faces[i] for i in cluster_indices]
            cluster_embeddings = [embeddings[i] for i in cluster_indices]

            # Compute average embedding
            avg_embedding = np.mean(cluster_embeddings, axis=0)

            # Select sample faces (up to 5)
            avg_norm = np.linalg.norm(avg_embedding)
            scored = []
            for face, emb in zip(cluster_faces, cluster_embeddings):
                emb_norm = np.linalg.norm(emb)
                if emb_norm > 0 and avg_norm > 0:
                    sim = float(np.dot(emb, avg_embedding) / (emb_norm * avg_norm))
                else:
                    sim = -1.0
                conf = face.confidence or 0.0
                area = (face.bbox_w or 0) * (face.bbox_h or 0)
                scored.append((sim, conf, area, face))
            scored.sort(reverse=True, key=lambda s: (s[0], s[1], s[2]))
            sample_faces = [s[3] for s in scored[:5]]

            cluster = FaceCluster(
                cluster_id=int(label),
                face_ids=[f.id for f in cluster_faces if f.id is not None],
                sample_faces=sample_faces,
                avg_embedding=avg_embedding,
            )
            clusters.append(cluster)

        logger.info(f"Created {len(clusters)} face clusters from {len(valid_faces)} faces")
        return clusters

    # ==========================================================================
    # Face Matching
    # ==========================================================================

    def load_person_embeddings(self) -> None:
        """Load all person embeddings into cache."""
        self._person_embeddings.clear()

        persons = self.db.get_all_persons()
        for person in persons:
            if person.id is None:
                continue

            # Get all faces for this person
            faces = self.db.get_faces_for_person(person.id)

            embeddings = []
            for face in faces:
                if face.embedding:
                    emb = self._deserialize_embedding(face.embedding)
                    age = face.estimated_age or 25  # Default adult
                    stage = AgeStage.from_age(age)
                    embeddings.append((stage, emb))

            if embeddings:
                self._person_embeddings[person.id] = embeddings

    def match_face(
        self,
        face: Face,
        threshold: Optional[float] = None,
    ) -> Optional[FaceMatch]:
        """Try to match a face to a known person.

        Args:
            face: Face to match
            threshold: Minimum similarity threshold

        Returns:
            FaceMatch if found, None otherwise
        """
        if not face.embedding:
            return None

        if not self._person_embeddings:
            self.load_person_embeddings()

        emb = self._deserialize_embedding(face.embedding)
        face_age = face.estimated_age or 25
        face_stage = AgeStage.from_age(face_age)

        best_match: Optional[FaceMatch] = None
        threshold = threshold if threshold is not None else self.match_threshold
        best_similarity = threshold

        for person_id, person_embeddings in self._person_embeddings.items():
            for stage, person_emb in person_embeddings:
                similarity = self.compute_similarity(emb, person_emb)

                # Boost similarity for same age stage
                if stage == face_stage:
                    similarity += 0.05

                if similarity > best_similarity:
                    best_similarity = similarity
                    person = self.db.get_person(person_id)
                    best_match = FaceMatch(
                        person_id=person_id,
                        person_name=person.name if person else None,
                        similarity=similarity,
                        age_stage=face_stage,
                    )

        return best_match

    def match_and_assign_faces(
        self,
        faces: Optional[list[Face]] = None,
        threshold: Optional[float] = None,
        auto_assign: bool = True,
    ) -> tuple[int, int]:
        """Match unassigned faces to known persons.

        Args:
            faces: Faces to match (if None, gets unassigned from DB)
            threshold: Minimum similarity for auto-assignment
            auto_assign: Whether to automatically assign matches

        Returns:
            Tuple of (matches_found, faces_assigned)
        """
        if faces is None:
            faces = self.db.get_unassigned_faces(min_confidence=self.det_conf_threshold)

        self.progress.phase = "matching"
        self._notify_progress()

        matches_found = 0
        faces_assigned = 0

        threshold = threshold if threshold is not None else self.match_threshold
        for face in faces:
            if self._cancel_event.is_set():
                break

            match = self.match_face(face, threshold)
            if match:
                matches_found += 1

                if auto_assign and match.similarity >= threshold:
                    # Assign face to person
                    self.db.assign_face_to_person(face.id, match.person_id)
                    faces_assigned += 1

                    # Update person's photo count
                    self.db.update_person_photo_count(match.person_id)

        self.progress.faces_matched = faces_assigned
        self._notify_progress()

        return matches_found, faces_assigned

    def find_more_faces_for_person(
        self,
        person_id: int,
        threshold: Optional[float] = None,
        auto_assign: bool = True,
    ) -> tuple[int, int]:
        """Find and assign unassigned faces that match a specific person.

        Unlike match_and_assign_faces which matches against all people,
        this method only looks for faces that match the specified person.

        Args:
            person_id: ID of the person to find more faces for
            threshold: Minimum similarity threshold (default: 0.8)
            auto_assign: Whether to automatically assign matching faces

        Returns:
            Tuple of (matches_found, faces_assigned)
        """
        # Get person and their embeddings
        person = self.db.get_person(person_id)
        if not person:
            logger.warning(f"Person {person_id} not found")
            return 0, 0

        if person_id not in self._person_embeddings:
            self.load_person_embeddings()

        if person_id not in self._person_embeddings:
            logger.warning(f"No embeddings found for person {person_id}")
            return 0, 0

        person_embeddings = self._person_embeddings[person_id]

        # Get unassigned faces
        faces = self.db.get_unassigned_faces(min_confidence=self.det_conf_threshold)

        self.progress.phase = "matching"
        self._notify_progress()

        threshold = threshold if threshold is not None else 0.8
        matches_found = 0
        faces_assigned = 0

        for face in faces:
            if self._cancel_event.is_set():
                break

            if not face.embedding:
                continue

            emb = self._deserialize_embedding(face.embedding)
            face_age = face.estimated_age or 25
            face_stage = AgeStage.from_age(face_age)

            # Check similarity against this specific person only
            best_similarity = 0.0
            for stage, person_emb in person_embeddings:
                similarity = self.compute_similarity(emb, person_emb)

                # Boost similarity for same age stage
                if stage == face_stage:
                    similarity += 0.05

                if similarity > best_similarity:
                    best_similarity = similarity

            if best_similarity >= threshold:
                matches_found += 1

                if auto_assign:
                    self.db.assign_face_to_person(face.id, person_id)
                    faces_assigned += 1
                    self.db.update_person_photo_count(person_id)

        self.progress.faces_matched = faces_assigned
        self._notify_progress()

        logger.info(f"Found {matches_found} matches for person {person_id} ({person.name}), assigned {faces_assigned}")
        return matches_found, faces_assigned

    # ==========================================================================
    # Cross-Age Cluster Linking
    # ==========================================================================

    # Thresholds for cross-age matching
    AUTO_ASSIGN_THRESHOLD = 0.85  # Auto-assign clusters above this similarity
    SUGGEST_THRESHOLD = 0.65      # Suggest clusters between this and auto threshold

    def find_intermediate_clusters(
        self,
        person_id: int,
        clusters: list,
    ) -> tuple[list, list[tuple]]:
        """Find clusters that may be the same person at intermediate ages.

        Uses embeddings from a person at known ages to find clusters that fall
        between them temporally, suggesting they may be the same person.

        Args:
            person_id: ID of the person to find intermediate clusters for
            clusters: List of FaceCluster objects to search

        Returns:
            Tuple of:
            - auto_assigned_clusters: Clusters above AUTO_ASSIGN_THRESHOLD (0.85)
            - suggested_clusters_with_scores: List of (cluster, score) for review (0.65-0.85)
        """
        person = self.db.get_person(person_id)
        if not person:
            return [], []

        # Load person embeddings if needed
        if person_id not in self._person_embeddings:
            self.load_person_embeddings()

        if person_id not in self._person_embeddings:
            return [], []

        person_embeddings = self._person_embeddings[person_id]
        if not person_embeddings:
            return [], []

        auto_assigned = []
        suggestions = []

        for cluster in clusters:
            # Skip clusters already assigned to someone
            if not cluster.face_ids:
                continue

            # Get sample faces from cluster
            sample_faces = self.db.get_faces_by_ids(cluster.face_ids[:10])
            if not sample_faces:
                continue

            # Compute best similarity to person's embeddings
            best_similarity = 0.0

            for face in sample_faces:
                if not face.embedding:
                    continue

                emb = self._deserialize_embedding(face.embedding)
                face_age = face.estimated_age

                for stage, person_emb in person_embeddings:
                    similarity = self.compute_similarity(emb, person_emb)

                    # Boost if cluster's estimated age falls between known ages
                    if face_age and person.birth_year:
                        expected_age = face_age
                        stage_age = stage.mid_age() if hasattr(stage, 'mid_age') else 25
                        # Small boost for intermediate ages
                        if abs(expected_age - stage_age) < 5:
                            similarity += 0.02

                    if similarity > best_similarity:
                        best_similarity = similarity

            # Categorize based on similarity
            if best_similarity >= self.AUTO_ASSIGN_THRESHOLD:
                auto_assigned.append(cluster)
            elif best_similarity >= self.SUGGEST_THRESHOLD:
                suggestions.append((cluster, best_similarity))

        # Sort suggestions by score (highest first)
        suggestions.sort(key=lambda x: x[1], reverse=True)

        return auto_assigned, suggestions

    def link_person_across_ages(self, person_id: int) -> tuple[int, int]:
        """Auto-assign high-confidence clusters and return suggestion count.

        Called after naming/assigning a person to find related clusters.

        Args:
            person_id: ID of the person to link across ages

        Returns:
            Tuple of (auto_assigned_count, suggestion_count)
        """
        # Get current clusters
        run = self.db.get_latest_face_cluster_run()
        if not run:
            return 0, 0

        run_id, _ = run
        cluster_data = self.db.get_face_clusters_for_run(run_id)

        # Convert to FaceCluster objects
        clusters = []
        for cluster_id, face_ids in cluster_data:
            # Only include unassigned clusters
            faces = self.db.get_faces_by_ids(face_ids[:5])
            if faces and all(f.person_id is None for f in faces):
                sample = self.db.get_faces_by_ids(face_ids[:5])
                clusters.append(FaceCluster(
                    cluster_id=cluster_id,
                    face_ids=face_ids,
                    sample_faces=sample,
                ))

        auto_assigned, suggestions = self.find_intermediate_clusters(person_id, clusters)

        # Auto-assign high-confidence matches
        auto_count = 0
        for cluster in auto_assigned:
            for face_id in cluster.face_ids:
                self.db.assign_face_to_person(face_id, person_id)
                auto_count += 1
            self.db.update_person_photo_count(person_id)

        logger.info(
            f"Cross-age linking for person {person_id}: "
            f"auto-assigned {auto_count} faces from {len(auto_assigned)} clusters, "
            f"{len(suggestions)} clusters suggested for review"
        )

        return len(auto_assigned), len(suggestions)

    # ==========================================================================
    # Person Management
    # ==========================================================================

    def create_person_from_cluster(
        self,
        cluster: FaceCluster,
        name: str,
        birth_year: Optional[int] = None,
    ) -> Optional[int]:
        """Create a person from a face cluster.

        Args:
            cluster: FaceCluster to convert to person
            name: Name for the person
            birth_year: Optional birth year for age tracking

        Returns:
            Person ID if created, None otherwise
        """
        # Create person
        person = Person(
            name=name,
            birth_year=birth_year,
            photo_count=len(cluster.face_ids),
        )

        # Get reference photo (first face's file)
        if cluster.sample_faces:
            ref_face = cluster.sample_faces[0]
            person.reference_photo_id = ref_face.file_id

        person_id = self.db.add_person(person)

        # Assign all faces to person
        for face_id in cluster.face_ids:
            self.db.assign_face_to_person(face_id, person_id)

        # Refresh embedding cache
        self.load_person_embeddings()

        logger.info(f"Created person '{name}' with {len(cluster.face_ids)} faces")
        return person_id

    def assign_cluster_to_person(self, cluster: FaceCluster, person_id: int) -> None:
        """Assign all faces in a cluster to an existing person."""
        for face_id in cluster.face_ids:
            self.db.assign_face_to_person(face_id, person_id)

        # Refresh embedding cache
        self.load_person_embeddings()
        logger.info(f"Assigned cluster with {len(cluster.face_ids)} faces to person {person_id}")

    def merge_clusters(
        self,
        cluster_ids: list[int],
        clusters: list[FaceCluster],
        name: str,
        birth_year: Optional[int] = None,
    ) -> Optional[int]:
        """Merge multiple clusters into a single person.

        Args:
            cluster_ids: IDs of clusters to merge
            clusters: List of all clusters (to find by ID)
            name: Name for the person
            birth_year: Optional birth year

        Returns:
            Person ID if created, None otherwise
        """
        # Collect all face IDs
        all_face_ids = []
        sample_faces = []

        for cluster in clusters:
            if cluster.cluster_id in cluster_ids:
                all_face_ids.extend(cluster.face_ids)
                sample_faces.extend(cluster.sample_faces[:2])

        if not all_face_ids:
            return None

        # Create merged cluster
        merged = FaceCluster(
            cluster_id=-1,
            face_ids=all_face_ids,
            sample_faces=sample_faces[:5],
        )

        return self.create_person_from_cluster(merged, name, birth_year)

    def split_cluster(
        self,
        cluster: FaceCluster,
        face_ids_to_remove: list[int],
    ) -> FaceCluster:
        """Split faces out of a cluster.

        Args:
            cluster: Original cluster
            face_ids_to_remove: Face IDs to move to new cluster

        Returns:
            New cluster with removed faces
        """
        # Remove from original
        remaining = [fid for fid in cluster.face_ids if fid not in face_ids_to_remove]
        cluster.face_ids = remaining
        cluster.sample_faces = [f for f in cluster.sample_faces if f.id not in face_ids_to_remove]

        # Create new cluster
        removed_faces = [f for f in cluster.sample_faces if f.id in face_ids_to_remove]
        new_cluster = FaceCluster(
            cluster_id=cluster.cluster_id + 1000,  # Offset to avoid collision
            face_ids=face_ids_to_remove,
            sample_faces=removed_faces[:5],
        )

        return new_cluster

    # ==========================================================================
    # Temporal Bridging
    # ==========================================================================

    def build_temporal_chain(
        self,
        person_id: int,
        rebuild: bool = False,
    ) -> bool:
        """Build temporal chain for age progression tracking.

        Links faces through time using relaxed thresholds for
        temporally adjacent photos.

        Args:
            person_id: Person to build chain for
            rebuild: Whether to rebuild from scratch

        Returns:
            True if chain was successfully built
        """
        person = self.db.get_person(person_id)
        if not person or not person.birth_year:
            logger.warning(f"Person {person_id} needs birth_year for temporal bridging")
            return False

        # Get all faces for person, ordered by photo date
        faces = self.db.get_faces_for_person(person_id)
        if len(faces) < 2:
            return True  # Nothing to chain

        # Get file dates for each face
        face_dates: list[tuple[Face, Optional[datetime]]] = []
        for face in faces:
            file_record = self.db.get_file(face.file_id)
            if file_record:
                # Try to get EXIF date
                metadata = self.db.get_metadata(face.file_id)
                date = metadata.exif_date if metadata else file_record.modified
                face_dates.append((face, date))

        # Sort by date
        face_dates.sort(key=lambda x: x[1] or datetime.min)

        # Build chain by connecting temporally adjacent faces
        for i in range(len(face_dates) - 1):
            face1, date1 = face_dates[i]
            face2, date2 = face_dates[i + 1]

            if not face1.embedding or not face2.embedding:
                continue

            # Calculate time gap
            if date1 and date2:
                gap_days = (date2 - date1).days
            else:
                gap_days = 365  # Assume 1 year if unknown

            # Determine threshold based on time gap
            if gap_days <= 1:
                threshold = self.TEMPORAL_THRESHOLD_SAME_DAY
            elif gap_days <= 30:
                threshold = self.TEMPORAL_THRESHOLD_SAME_MONTH
            elif gap_days <= 365:
                threshold = self.TEMPORAL_THRESHOLD_SAME_YEAR
            else:
                threshold = self.TEMPORAL_THRESHOLD_DIFFERENT_YEARS

            # Check similarity
            emb1 = self._deserialize_embedding(face1.embedding)
            emb2 = self._deserialize_embedding(face2.embedding)
            similarity = self.compute_similarity(emb1, emb2)

            if similarity < threshold:
                logger.debug(
                    f"Chain break: {face1.id} -> {face2.id}, "
                    f"similarity={similarity:.3f}, threshold={threshold}"
                )

        logger.info(f"Built temporal chain for person {person_id}")
        return True

    def find_chain_gaps(self, person_id: int) -> list[tuple[int, int, float]]:
        """Find gaps in temporal chain where faces might be missing.

        Args:
            person_id: Person to check

        Returns:
            List of (year_start, year_end, gap_size) tuples
        """
        person = self.db.get_person(person_id)
        if not person or not person.birth_year:
            return []

        faces = self.db.get_faces_for_person(person_id)

        # Get years covered
        years_covered = set()
        for face in faces:
            file_record = self.db.get_file(face.file_id)
            if file_record and file_record.modified:
                years_covered.add(file_record.modified.year)

        if not years_covered:
            return []

        # Find gaps
        gaps = []
        min_year = min(years_covered)
        max_year = max(years_covered)

        gap_start = None
        for year in range(min_year, max_year + 1):
            if year not in years_covered:
                if gap_start is None:
                    gap_start = year
            else:
                if gap_start is not None:
                    gaps.append((gap_start, year - 1, year - gap_start))
                    gap_start = None

        return gaps

    # ==========================================================================
    # Search & Retrieval
    # ==========================================================================

    def find_similar_faces(
        self,
        face: Face,
        limit: int = 20,
        threshold: Optional[float] = None,
    ) -> list[tuple[Face, float]]:
        """Find faces similar to a given face.

        Args:
            face: Face to find matches for
            limit: Maximum results
            threshold: Minimum similarity

        Returns:
            List of (Face, similarity) tuples
        """
        if not face.embedding:
            return []

        emb = self._deserialize_embedding(face.embedding)

        # Get all faces
        all_faces = self.db.get_all_faces()

        # Compute similarities
        results = []
        threshold = threshold if threshold is not None else self.match_threshold
        for other_face in all_faces:
            if other_face.id == face.id:
                continue
            if not other_face.embedding:
                continue

            other_emb = self._deserialize_embedding(other_face.embedding)
            similarity = self.compute_similarity(emb, other_emb)

            if similarity >= threshold:
                results.append((other_face, similarity))

        # Sort by similarity
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_person_timeline(
        self,
        person_id: int,
    ) -> list[tuple[int, list[Face]]]:
        """Get faces organized by year for timeline view.

        Args:
            person_id: Person to get timeline for

        Returns:
            List of (year, faces) tuples
        """
        faces = self.db.get_faces_for_person(person_id)

        # Group by year
        by_year: dict[int, list[Face]] = {}
        for face in faces:
            file_record = self.db.get_file(face.file_id)
            if file_record and file_record.modified:
                year = file_record.modified.year
                if year not in by_year:
                    by_year[year] = []
                by_year[year].append(face)

        # Sort by year
        return sorted(by_year.items())

    def cancel(self) -> None:
        """Cancel ongoing operation."""
        self._cancel_event.set()
        logger.info("Face analysis cancelled")
