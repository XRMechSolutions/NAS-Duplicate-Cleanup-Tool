"""Face detection and recognition module.

Uses InsightFace (buffalo_l model) for face detection, embedding extraction,
and recognition. Includes temporal bridging for age progression tracking.
"""

import os
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import Event

import numpy as np

from ..db.database import Database
from ..db.models import Face, FileRecord, Person
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
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    logger.warning("InsightFace not available. Face recognition disabled.")

try:
    from sklearn.cluster import DBSCAN
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

    def mid_age(self) -> int:
        """Return midpoint age for this life stage."""
        return {
            AgeStage.BABY: 1,
            AgeStage.TODDLER: 3,
            AgeStage.CHILD: 8,
            AgeStage.TEEN: 15,
            AgeStage.ADULT: 25,
        }[self]


@dataclass
class DetectedFace:
    """A face detected in an image."""
    bbox: tuple[int, int, int, int]  # x, y, width, height
    embedding: np.ndarray            # 512-dim vector
    confidence: float
    estimated_age: int | None = None
    estimated_gender: str | None = None
    landmarks: np.ndarray | None = None


@dataclass
class FaceMatch:
    """Result of matching a face to a known person."""
    person_id: int
    person_name: str | None
    similarity: float
    age_stage: AgeStage | None = None
    demotion_reason: str | None = None  # Why this was demoted to suggestion


@dataclass
class FaceCluster:
    """A cluster of similar faces (potential person)."""
    cluster_id: int
    face_ids: list[int]
    sample_faces: list[Face]  # Representative faces
    avg_embedding: np.ndarray | None = None
    person_id: int | None = None  # If assigned
    person_name: str | None = None


@dataclass
class TemporalChainResult:
    """Result of building a temporal chain for a person."""
    person_id: int
    total_links: int = 0
    strong_links: int = 0
    weak_links: int = 0
    breaks: int = 0
    gap_years: int = 0


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

    # Chain confidence decay per hop for transitive matching
    CHAIN_CONFIDENCE_DECAY = {1: 1.0, 2: 0.85, 3: 0.70}
    CHAIN_MAX_HOPS = 3

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

        self._model: FaceAnalysis | None = None
        self._model_loaded = False

        # Progress tracking
        self.progress = FaceAnalysisProgress()
        self._cancel_event = Event()
        self._progress_callback: Callable[[FaceAnalysisProgress], None] | None = None

        # Cache for person embeddings
        self._person_embeddings: dict[int, list[tuple[AgeStage, np.ndarray]]] = {}

    def set_progress_callback(
        self, callback: Callable[[FaceAnalysisProgress], None] | None
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
        if not self._model_loaded and not self.load_model():
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
                except Exception as e:
                    # Attempt JPEG recovery for corrupt files
                    if image_path.lower().endswith(('.jpg', '.jpeg')):
                        logger.warning(f"Could not read image: {image_path} - {e}")
                        logger.info(f"Attempting JPEG recovery for: {image_path}")

                        from ..utils.jpeg_recovery import recover_jpeg_for_analysis
                        recovered_path = recover_jpeg_for_analysis(image_path)

                        if recovered_path:
                            logger.info(f"Successfully recovered JPEG: {image_path}")
                            try:
                                # Try to load recovered image
                                with Image.open(recovered_path) as pil_img:
                                    pil_img = ImageOps.exif_transpose(pil_img)
                                    pil_img = pil_img.convert("RGB")
                                    img = np.array(pil_img)[:, :, ::-1]
                            except Exception as e2:
                                logger.error(f"Failed to load recovered JPEG: {e2}")
                                return []
                        else:
                            logger.warning(f"JPEG recovery failed for: {image_path}")
                            return []
                    else:
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

        if file_record.path.lower().endswith('.pdf'):
            return self._analyze_pdf(file_record)

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

    def _analyze_pdf(self, file_record: FileRecord) -> list[Face]:
        """Detect faces across all pages of a PDF.

        When pdf_extract_pages is enabled, extracts pages to persistent JPEGs
        saved alongside the PDF and runs face detection on those. Faces are
        stored against the extracted JPEG file IDs, not the PDF file ID.

        When disabled, falls back to temp-file rendering.
        """
        config = get_config()
        if not config.ai.pdf_extract_pages:
            return self._analyze_pdf_temp(file_record)

        extracted = self._ensure_pdf_extracted(file_record)
        if not extracted:
            self.db.mark_faces_analyzed(file_record.id, faces_found=0)
            return []

        all_faces = []
        for page_file_record in extracted:
            # Run normal image face detection on each extracted JPEG
            detected = self.detect_faces(page_file_record.path)
            if not detected:
                self.db.mark_faces_analyzed(page_file_record.id, faces_found=0)
                continue

            for det in detected:
                face = Face(
                    file_id=page_file_record.id,
                    bbox_x=det.bbox[0],
                    bbox_y=det.bbox[1],
                    bbox_w=det.bbox[2],
                    bbox_h=det.bbox[3],
                    embedding=self._serialize_embedding(det.embedding),
                    confidence=det.confidence,
                    estimated_age=det.estimated_age,
                    estimated_gender=det.estimated_gender,
                )
                face_id = self.db.add_face(face)
                face.id = face_id
                all_faces.append(face)

            self.db.mark_faces_analyzed(page_file_record.id, faces_found=len(
                [f for f in all_faces if f.file_id == page_file_record.id]
            ))

        self.db.mark_faces_analyzed(file_record.id, faces_found=len(all_faces))
        return all_faces

    def _ensure_pdf_extracted(self, file_record: FileRecord) -> list[FileRecord]:
        """Ensure PDF pages are extracted to persistent JPEG files.

        If already extracted, returns existing FileRecords from DB.
        Otherwise renders each page and registers the JPEGs.

        Returns:
            List of FileRecords for the extracted page JPEGs, or empty on failure.
        """
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF not installed - cannot extract PDF pages")
            return []

        # Check if already extracted
        if self.db.is_pdf_extracted(file_record.id):
            extractions = self.db.get_pdf_extractions(file_record.id)
            records = []
            for _page_num, extracted_file_id in extractions:
                rec = self.db.get_file(extracted_file_id)
                if rec and os.path.exists(rec.path):
                    records.append(rec)
                else:
                    logger.warning(
                        f"Extracted JPEG missing for PDF {file_record.path} "
                        f"page {_page_num}, will re-extract"
                    )
                    records = []
                    break
            if records:
                return records

        # Render pages to persistent JPEGs
        try:
            doc = fitz.open(file_record.path)
            page_count = len(doc)
            doc.close()
        except Exception as e:
            logger.error(f"Cannot open PDF {file_record.path}: {e}")
            return []

        pdf_path = Path(file_record.path)
        pdf_stem = pdf_path.stem
        pdf_dir = pdf_path.parent

        extracted_records = []
        for page_num in range(page_count):
            # Build output path: document-1.jpg, document-2.jpg, ...
            jpeg_name = f"{pdf_stem}-{page_num + 1}.jpg"
            jpeg_path = pdf_dir / jpeg_name

            # Skip if file already exists on disk (not from our extraction)
            if jpeg_path.exists():
                existing = self.db.get_file_by_path_any(str(jpeg_path))
                if existing and self.db.is_pdf_extracted(file_record.id):
                    # Our own previous extraction - reuse it
                    pass
                elif existing:
                    logger.warning(
                        f"Cannot extract PDF page: {jpeg_path} already exists "
                        f"(not from extraction). Skipping PDF {file_record.path}."
                    )
                    return []
                else:
                    logger.warning(
                        f"Cannot extract PDF page: {jpeg_path} already exists on disk. "
                        f"Skipping PDF {file_record.path}."
                    )
                    return []

            # Render the page
            rendered_path = self._render_pdf_page_to_file(
                str(pdf_path), page_num, str(pdf_dir), zoom=2.0,
                output_filename=jpeg_name,
            )
            if not rendered_path:
                logger.warning(
                    f"Failed to render page {page_num} of {file_record.path}"
                )
                continue

            # Register the JPEG in the files table
            jpeg_stat = os.stat(rendered_path)
            from datetime import datetime as dt
            page_record = FileRecord(
                drive_id=file_record.drive_id,
                path=str(jpeg_path),
                filename=jpeg_name,
                size=jpeg_stat.st_size,
                created=dt.fromtimestamp(jpeg_stat.st_ctime),
                modified=dt.fromtimestamp(jpeg_stat.st_mtime),
                file_type=".jpg",
                mime_type="image/jpeg",
                scan_date=dt.now(),
            )
            page_file_id = self.db.add_file(page_record)
            page_record.id = page_file_id

            # Link extraction
            self.db.add_pdf_extraction(file_record.id, page_num, page_file_id)
            extracted_records.append(page_record)

        if extracted_records:
            logger.info(
                f"Extracted {len(extracted_records)} pages from "
                f"{file_record.path}"
            )

        return extracted_records

    def _analyze_pdf_temp(self, file_record: FileRecord) -> list[Face]:
        """Detect faces across PDF pages using temporary files (fallback)."""
        import tempfile
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF not installed - cannot analyze PDF for faces")
            self.db.mark_faces_analyzed(file_record.id, faces_found=0)
            return []

        try:
            doc = fitz.open(file_record.path)
            page_count = len(doc)
            doc.close()
        except Exception as e:
            logger.error(f"Cannot open PDF {file_record.path}: {e}")
            self.db.mark_faces_analyzed(file_record.id, faces_found=0)
            return []

        all_faces = []
        with tempfile.TemporaryDirectory(prefix="duplicleaner_pdf_faces_") as tmp_dir:
            for page_num in range(page_count):
                page_img_path = self._render_pdf_page_to_file(
                    file_record.path, page_num, tmp_dir
                )
                if not page_img_path:
                    continue

                detected = self.detect_faces(page_img_path)
                for det in detected:
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
                        page_number=page_num,
                    )
                    face_id = self.db.add_face(face)
                    face.id = face_id
                    all_faces.append(face)

        self.db.mark_faces_analyzed(file_record.id, faces_found=len(all_faces))
        return all_faces

    @staticmethod
    def _render_pdf_page_to_file(
        pdf_path: str,
        page_num: int,
        output_dir: str,
        zoom: float = 2.0,
        output_filename: str | None = None,
    ) -> str | None:
        """Render a PDF page to a JPEG file.

        Args:
            pdf_path: Path to PDF file.
            page_num: 0-indexed page number.
            output_dir: Directory to write the JPEG into.
            zoom: Rendering zoom factor.
            output_filename: If provided, use this filename instead of page_N.jpg.

        Returns:
            Path to rendered image or None on failure.
        """
        try:
            import fitz
            doc = fitz.open(pdf_path)
            if page_num >= len(doc):
                doc.close()
                return None
            page = doc[page_num]
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            fname = output_filename or f"page_{page_num}.jpg"
            out_path = os.path.join(output_dir, fname)
            pix.save(out_path)
            doc.close()
            return out_path
        except Exception as e:
            logger.debug(f"Failed to render PDF page {page_num}: {e}")
            return None

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
        faces: list[Face] | None = None,
        eps: float | None = None,
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
            for face, emb in zip(cluster_faces, cluster_embeddings, strict=False):
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
            self._load_single_person_embeddings(person)

    def refresh_person_embeddings(self, person_id: int) -> None:
        """Refresh cached embeddings for a single person.

        More efficient than reloading all persons when only one changed.
        """
        person = self.db.get_person(person_id)
        if not person or person.id is None:
            self._person_embeddings.pop(person_id, None)
            return
        self._load_single_person_embeddings(person)

    def _load_single_person_embeddings(self, person: Person) -> None:
        """Load embeddings for one person into the cache.

        When the person has a birth_year and the face has a photo date,
        computes the actual age at photo time for more accurate stage assignment.
        """
        if person.id is None:
            return

        faces = self.db.get_faces_for_person(person.id)

        embeddings = []
        for face in faces:
            if not face.embedding:
                continue

            emb = self._deserialize_embedding(face.embedding)

            # Try to compute actual age from birth_year + photo date
            age = face.estimated_age or 25  # Default adult
            if person.birth_year and face.id is not None:
                photo_date = self.db.get_photo_date_for_face(face.id)
                if photo_date:
                    actual_age = photo_date.year - person.birth_year
                    if 0 <= actual_age <= 120:
                        age = actual_age

            stage = AgeStage.from_age(age)
            embeddings.append((stage, emb))

        if embeddings:
            self._person_embeddings[person.id] = embeddings
        else:
            self._person_embeddings.pop(person.id, None)

    # ------------------------------------------------------------------
    # Intelligent assignment helpers (4.1)
    # ------------------------------------------------------------------

    def _get_photo_date(self, face: Face) -> datetime | None:
        """Get the EXIF photo date for a face's source file.

        Uses only EXIF date (not file system dates) since file dates
        are unreliable for age plausibility checks.
        """
        if face.id is None:
            return None
        return self.db.get_photo_date_for_face(face.id)

    def _check_age_plausibility(
        self,
        person: Person,
        face: Face,
        photo_date: datetime | None,
    ) -> tuple[bool, str | None]:
        """Check whether assigning this face to this person is age-plausible.

        Returns:
            (is_plausible, reason_if_not)
            If person has no birth_year or photo_date is None, returns (True, None).
        """
        if person.birth_year is None or photo_date is None:
            return (True, None)

        # Pre-birth impossibility guard
        if photo_date.year < person.birth_year:
            sibling_hint = ""
            try:
                siblings = self.db.get_related_persons(person.id, "sibling")
                if siblings:
                    names = ", ".join(s.name for s in siblings if s.name)
                    sibling_hint = f" Known siblings: {names}"
            except Exception:
                pass
            reason = (
                f"Photo predates {person.name}'s birth ({person.birth_year}). "
                f"Could this be a sibling of {person.name}?{sibling_hint}"
            )
            return (False, reason)

        # Age plausibility check
        expected_age = photo_date.year - person.birth_year
        if face.estimated_age is not None:
            # Tolerance: wider for children whose faces change rapidly
            tolerance = 10 if expected_age < 12 else 8
            if abs(face.estimated_age - expected_age) > tolerance:
                reason = (
                    f"Estimated age {face.estimated_age} doesn't match "
                    f"expected age {expected_age} for {person.name}"
                )
                return (False, reason)

        return (True, None)

    def _resolve_per_photo_conflicts(
        self,
        candidates: list[tuple[Face, FaceMatch, str | None]],
    ) -> tuple[list[tuple[Face, FaceMatch]], list[tuple[Face, FaceMatch, str]]]:
        """Resolve per-photo conflicts using greedy bipartite matching.

        In any single photo, each person should appear at most once.
        When two faces in the same photo both match the same person,
        only the higher-confidence match is kept; the other is demoted.

        Args:
            candidates: list of (face, match, age_reason) tuples

        Returns:
            (assignable, demoted) where demoted includes a reason string.
        """
        # Group by file_id
        by_file: dict[int, list[tuple[Face, FaceMatch, str | None]]] = {}
        for face, match, age_reason in candidates:
            by_file.setdefault(face.file_id, []).append((face, match, age_reason))

        assignable: list[tuple[Face, FaceMatch]] = []
        demoted: list[tuple[Face, FaceMatch, str]] = []

        for _file_id, group in by_file.items():
            # Sort by similarity descending (highest first)
            group.sort(key=lambda x: x[1].similarity, reverse=True)

            assigned_persons: set[int] = set()
            assigned_faces: set[int | None] = set()

            for face, match, age_reason in group:
                if age_reason is not None:
                    demoted.append((face, match, age_reason))
                elif match.person_id in assigned_persons:
                    demoted.append((
                        face,
                        match,
                        "Higher-confidence match exists in this photo",
                    ))
                elif face.id in assigned_faces:
                    continue  # shouldn't happen, but guard
                else:
                    assigned_persons.add(match.person_id)
                    assigned_faces.add(face.id)
                    assignable.append((face, match))

        return assignable, demoted

    def match_face(
        self,
        face: Face,
        threshold: float | None = None,
    ) -> FaceMatch | None:
        """Try to match a face to a known person.

        Runs a standard embedding comparison first. If no match is found,
        runs a temporal-aware pass that uses relaxed thresholds based on
        the temporal distance between the candidate face and each person's
        nearest-in-time face.

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

        best_match: FaceMatch | None = None
        threshold = threshold if threshold is not None else self.match_threshold
        best_similarity = threshold

        # Standard pass: compare against all person embeddings
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

        if best_match is not None:
            return best_match

        # Temporal-aware pass: use relaxed thresholds based on time gap
        return self._temporal_match_face(face, emb)

    def _temporal_match_face(
        self,
        face: Face,
        emb: np.ndarray,
    ) -> FaceMatch | None:
        """Second-pass matching using temporal proximity for relaxed thresholds.

        For each person, finds the nearest-in-time face and uses a threshold
        based on the temporal distance. Only runs when the standard pass fails.

        Args:
            face: Face to match
            emb: Pre-deserialized embedding

        Returns:
            FaceMatch if found via temporal matching, None otherwise
        """
        if face.id is None:
            return None

        face_date = self.db.get_photo_date_for_face(face.id)
        if not face_date:
            return None

        face_age = face.estimated_age or 25
        face_stage = AgeStage.from_age(face_age)
        best_match: FaceMatch | None = None
        best_similarity = 0.0

        for person_id, person_embeddings in self._person_embeddings.items():
            # Get this person's faces to find the temporally nearest one
            person_faces = self.db.get_faces_for_person(person_id)

            # Find nearest-in-time face (check up to 20 for performance)
            nearest_gap_days: int | None = None
            nearest_similarity = 0.0

            for pf in person_faces[:20]:
                if not pf.embedding or pf.id is None:
                    continue

                pf_date = self.db.get_photo_date_for_face(pf.id)
                if not pf_date:
                    continue

                gap_days = abs((face_date - pf_date).days)
                pf_emb = self._deserialize_embedding(pf.embedding)
                similarity = self.compute_similarity(emb, pf_emb)

                if nearest_gap_days is None or gap_days < nearest_gap_days:
                    nearest_gap_days = gap_days
                    nearest_similarity = similarity
                elif gap_days == nearest_gap_days and similarity > nearest_similarity:
                    nearest_similarity = similarity

            if nearest_gap_days is None:
                continue

            # Use temporal threshold for this gap
            temporal_threshold = self._get_temporal_threshold(nearest_gap_days)

            if nearest_similarity > temporal_threshold and nearest_similarity > best_similarity:
                best_similarity = nearest_similarity
                person = self.db.get_person(person_id)
                best_match = FaceMatch(
                    person_id=person_id,
                    person_name=person.name if person else None,
                    similarity=nearest_similarity,
                    age_stage=face_stage,
                )

        return best_match

    def find_transitive_matches(
        self,
        face: Face,
        max_hops: int = 3,
    ) -> list[tuple[int, str | None, float, int]]:
        """Find persons reachable through temporal link chains (BFS).

        Walks the temporal link graph starting from faces similar to the
        given face, applying confidence decay per hop. Returns suggestions
        only - never auto-assigns.

        Args:
            face: Face to find transitive matches for
            max_hops: Maximum chain hops (default 3)

        Returns:
            List of (person_id, person_name, confidence, hops) tuples,
            sorted by confidence descending
        """
        if not face.embedding or face.id is None:
            return []

        max_hops = min(max_hops, self.CHAIN_MAX_HOPS)
        emb = self._deserialize_embedding(face.embedding)

        # Find faces directly similar to this one (entry points)
        similar = self.find_similar_faces(face, limit=10, threshold=0.4)
        if not similar:
            return []

        # BFS through temporal links
        # visited: face_id -> (min_hops, max_confidence)
        visited: dict[int, tuple[int, float]] = {}
        # person matches: person_id -> (confidence, hops)
        person_matches: dict[int, tuple[float, int]] = {}

        # Queue entries: (face_id, current_hops, accumulated_confidence)
        bfs_queue: list[tuple[int, int, float]] = []

        for sim_face, similarity in similar:
            if sim_face.id is None:
                continue
            bfs_queue.append((sim_face.id, 1, similarity))

            # Direct match - check if this similar face belongs to a person
            if sim_face.person_id is not None:
                decay = self.CHAIN_CONFIDENCE_DECAY.get(1, 0.5)
                conf = similarity * decay
                existing = person_matches.get(sim_face.person_id)
                if existing is None or conf > existing[0]:
                    person_matches[sim_face.person_id] = (conf, 1)

        while bfs_queue:
            current_face_id, hops, confidence = bfs_queue.pop(0)

            if hops > max_hops:
                continue

            # Skip if we already visited this face with better confidence
            prev = visited.get(current_face_id)
            if prev is not None and prev[1] >= confidence:
                continue
            visited[current_face_id] = (hops, confidence)

            # Get temporal links for this face's person
            current_face = self.db.get_face(current_face_id)
            if not current_face or current_face.person_id is None:
                continue

            links = self.db.get_temporal_links(current_face.person_id)
            for link in links:
                # Follow the link to the next face
                next_face_id = (
                    link["face_id_b"]
                    if link["face_id_a"] == current_face_id
                    else link["face_id_a"]
                )

                if next_face_id in visited:
                    continue

                link_sim = link.get("similarity", 0.0)
                next_hops = hops + 1
                decay = self.CHAIN_CONFIDENCE_DECAY.get(next_hops, 0.5)
                next_conf = confidence * link_sim * decay

                # Check if next face has a person assigned
                next_face = self.db.get_face(next_face_id)
                if next_face and next_face.person_id is not None:
                    existing = person_matches.get(next_face.person_id)
                    if existing is None or next_conf > existing[0]:
                        person_matches[next_face.person_id] = (next_conf, next_hops)

                if next_hops < max_hops:
                    bfs_queue.append((next_face_id, next_hops, next_conf))

        # Build results
        results: list[tuple[int, str | None, float, int]] = []
        for pid, (conf, hops) in person_matches.items():
            person = self.db.get_person(pid)
            name = person.name if person else None
            results.append((pid, name, conf, hops))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def match_and_assign_faces(
        self,
        faces: list[Face] | None = None,
        threshold: float | None = None,
        auto_assign: bool = True,
    ) -> tuple[int, int]:
        """Match unassigned faces to known persons.

        Uses per-photo conflict detection to prevent the same person
        being assigned to two faces in one image, and age plausibility
        checks when birth_year / EXIF date are available.

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

        threshold = threshold if threshold is not None else self.match_threshold

        # Collect all candidates first
        candidates: list[tuple[Face, FaceMatch, str | None]] = []
        for face in faces:
            if self._cancel_event.is_set():
                break

            match = self.match_face(face, threshold)
            if match:
                person = self.db.get_person(match.person_id)
                if person:
                    photo_date = self._get_photo_date(face)
                    _plausible, age_reason = self._check_age_plausibility(
                        person, face, photo_date,
                    )
                    candidates.append((face, match, age_reason))

        # Resolve per-photo conflicts
        assignable, _demoted = self._resolve_per_photo_conflicts(candidates)

        matches_found = len(candidates)
        faces_assigned = 0
        updated_person_ids: set[int] = set()

        if auto_assign:
            for face, match in assignable:
                self.db.assign_face_to_person(face.id, match.person_id)
                updated_person_ids.add(match.person_id)
                faces_assigned += 1

        for pid in updated_person_ids:
            self.db.update_person_photo_count(pid)

        self.progress.faces_matched = faces_assigned
        self._notify_progress()

        return matches_found, faces_assigned

    def rematch_all_faces(
        self,
        auto_threshold: float | None = None,
        suggest_threshold: float | None = None,
    ) -> tuple[int, list[tuple[int, str, Face, float, str | None]]]:
        """Re-match all unassigned faces against current known person embeddings.

        Scans every unassigned face and finds the best matching person.
        High-confidence matches are auto-assigned; lower-confidence matches
        are returned as suggestions for user review. Per-photo conflict
        detection prevents the same person being assigned twice in one photo,
        and age plausibility checks guard against impossible assignments.

        Args:
            auto_threshold: Min similarity for auto-assignment (default: match_threshold)
            suggest_threshold: Min similarity for suggestions (default: SUGGEST_THRESHOLD)

        Returns:
            Tuple of (auto_assigned_count, suggestions) where suggestions is a
            list of (person_id, person_name, face, similarity, reason) sorted
            by similarity desc. reason is None for normal suggestions, or a
            string explaining why the match was demoted.
        """
        if auto_threshold is None:
            auto_threshold = self.match_threshold
        if suggest_threshold is None:
            suggest_threshold = self.SUGGEST_THRESHOLD

        # Refresh person embeddings cache with latest assignments
        self.load_person_embeddings()

        if not self._person_embeddings:
            logger.info("No person embeddings found, nothing to re-match")
            return (0, [])

        faces = self.db.get_unassigned_faces(min_confidence=self.det_conf_threshold)
        if not faces:
            logger.info("No unassigned faces to re-match")
            return (0, [])

        self.progress.phase = "re-matching"
        self.progress.total_files = len(faces)
        self.progress.processed_files = 0
        self._notify_progress()

        # Phase 1: find best match per face
        all_candidates: list[tuple[Face, FaceMatch, str | None]] = []

        for face in faces:
            if self._cancel_event.is_set():
                break

            self.progress.processed_files += 1
            if self.progress.processed_files % 50 == 0:
                self._notify_progress()

            if not face.embedding:
                continue

            emb = self._deserialize_embedding(face.embedding)
            face_age = face.estimated_age or 25
            face_stage = AgeStage.from_age(face_age)

            best_similarity = 0.0
            best_person_id: int | None = None
            best_person_name: str | None = None

            for person_id, person_embeddings in self._person_embeddings.items():
                for stage, person_emb in person_embeddings:
                    similarity = self.compute_similarity(emb, person_emb)

                    # Boost similarity for same age stage
                    if stage == face_stage:
                        similarity += 0.05

                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_person_id = person_id
                        person = self.db.get_person(person_id)
                        best_person_name = person.name if person else None

            if best_person_id is not None and best_similarity >= suggest_threshold:
                match = FaceMatch(
                    person_id=best_person_id,
                    person_name=best_person_name,
                    similarity=best_similarity,
                    age_stage=face_stage,
                )
                # Age plausibility check
                person = self.db.get_person(best_person_id)
                if person:
                    photo_date = self._get_photo_date(face)
                    _plausible, age_reason = self._check_age_plausibility(
                        person, face, photo_date,
                    )
                else:
                    age_reason = None
                all_candidates.append((face, match, age_reason))

        # Phase 2: resolve per-photo conflicts
        assignable, demoted = self._resolve_per_photo_conflicts(all_candidates)

        auto_assigned = 0
        suggestions: list[tuple[int, str, Face, float, str | None]] = []
        updated_person_ids: set[int] = set()

        # Auto-assign high-confidence non-conflicting matches
        for face, match in assignable:
            if match.similarity >= auto_threshold:
                self.db.assign_face_to_person(face.id, match.person_id)
                updated_person_ids.add(match.person_id)
                auto_assigned += 1
            elif match.similarity >= suggest_threshold:
                suggestions.append((
                    match.person_id,
                    match.person_name or "",
                    face,
                    match.similarity,
                    None,
                ))

        # Demoted matches become suggestions with reason
        for face, match, reason in demoted:
            if match.similarity >= suggest_threshold:
                suggestions.append((
                    match.person_id,
                    match.person_name or "",
                    face,
                    match.similarity,
                    reason,
                ))

        # Update photo counts for all affected persons
        for pid in updated_person_ids:
            self.db.update_person_photo_count(pid)

        self.progress.faces_matched = auto_assigned
        self._notify_progress()

        # Sort suggestions by similarity descending
        suggestions.sort(key=lambda x: x[3], reverse=True)

        demoted_count = sum(1 for s in suggestions if s[4] is not None)
        logger.info(
            "Re-match complete: %d auto-assigned, %d suggestions (%d with conflicts) from %d unassigned faces",
            auto_assigned, len(suggestions), demoted_count, len(faces),
        )
        return (auto_assigned, suggestions)

    def find_more_faces_for_person(
        self,
        person_id: int,
        threshold: float | None = None,
        auto_assign: bool = True,
    ) -> tuple[int, int]:
        """Find and assign unassigned faces that match a specific person.

        Unlike match_and_assign_faces which matches against all people,
        this method only looks for faces that match the specified person.
        Applies per-photo conflict detection and age plausibility checks.

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

        # Collect all candidates first
        candidates: list[tuple[Face, FaceMatch, str | None]] = []

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
                match = FaceMatch(
                    person_id=person_id,
                    person_name=person.name,
                    similarity=best_similarity,
                    age_stage=face_stage,
                )
                photo_date = self._get_photo_date(face)
                _plausible, age_reason = self._check_age_plausibility(
                    person, face, photo_date,
                )
                candidates.append((face, match, age_reason))

        # Resolve per-photo conflicts
        assignable, _demoted = self._resolve_per_photo_conflicts(candidates)

        matches_found = len(candidates)
        faces_assigned = 0

        if auto_assign:
            for face, match in assignable:
                self.db.assign_face_to_person(face.id, person_id)
                faces_assigned += 1
            if faces_assigned > 0:
                self.db.update_person_photo_count(person_id)

        self.progress.faces_matched = faces_assigned
        self._notify_progress()

        logger.info(f"Found {matches_found} matches for person {person_id} ({person.name}), assigned {faces_assigned}")
        return matches_found, faces_assigned

    # ==========================================================================
    # Cross-Age Cluster Linking
    # ==========================================================================

    # Thresholds for cross-age matching
    AUTO_ASSIGN_THRESHOLD = 0.95  # Auto-assign only very high confidence matches
    SUGGEST_THRESHOLD = 0.35      # Lower threshold to show more potential matches for review

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
                        stage_age = stage.mid_age()
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
        birth_year: int | None = None,
    ) -> int | None:
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

        # Refresh embedding cache and build temporal chain
        self.refresh_person_embeddings(person_id)
        self.build_temporal_chain(person_id, _rebuild=True)

        logger.info(f"Created person '{name}' with {len(cluster.face_ids)} faces")
        return person_id

    def assign_cluster_to_person(self, cluster: FaceCluster, person_id: int) -> None:
        """Assign all faces in a cluster to an existing person."""
        for face_id in cluster.face_ids:
            self.db.assign_face_to_person(face_id, person_id)

        # Refresh embedding cache and rebuild temporal chain
        self.refresh_person_embeddings(person_id)
        self.build_temporal_chain(person_id, _rebuild=True)
        logger.info(f"Assigned cluster with {len(cluster.face_ids)} faces to person {person_id}")

    def merge_clusters(
        self,
        cluster_ids: list[int],
        clusters: list[FaceCluster],
        name: str,
        birth_year: int | None = None,
    ) -> int | None:
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
    # Age Estimation
    # ==========================================================================

    def _estimate_birth_year_from_faces(self, faces: list[Face]) -> int | None:
        """Estimate birth year from faces with estimated_age and photo dates.

        Uses median of (photo_year - estimated_age) to reduce outlier impact.

        Args:
            faces: Faces to estimate from

        Returns:
            Estimated birth year, or None if insufficient data
        """
        estimates: list[int] = []
        for face in faces:
            if face.estimated_age is None or face.id is None:
                continue
            photo_date = self.db.get_photo_date_for_face(face.id)
            if photo_date:
                estimates.append(photo_date.year - face.estimated_age)

        if not estimates:
            return None

        # Use median to reduce impact of inaccurate age estimates
        estimates.sort()
        mid = len(estimates) // 2
        if len(estimates) % 2 == 0:
            return (estimates[mid - 1] + estimates[mid]) // 2
        return estimates[mid]

    def estimate_birth_year(self, person_id: int) -> int | None:
        """Estimate birth year for a person from their face data.

        Computes median of (photo_year - estimated_age) across all faces
        that have both an AI age estimate and a photo date.

        Args:
            person_id: Person to estimate for

        Returns:
            Estimated birth year, or None if insufficient data
        """
        faces = self.db.get_faces_for_person(person_id)
        return self._estimate_birth_year_from_faces(faces)

    def get_age_estimation_accuracy(
        self, person_id: int
    ) -> list[dict]:
        """Compare AI age estimates to actual ages for diagnostics.

        Requires person to have a birth_year set. For each face with an
        estimated_age and photo date, computes the error.

        Args:
            person_id: Person to check

        Returns:
            List of dicts with face_id, photo_year, estimated_age,
            actual_age, error (estimated - actual)
        """
        person = self.db.get_person(person_id)
        if not person or not person.birth_year:
            return []

        faces = self.db.get_faces_for_person(person_id)
        results: list[dict] = []

        for face in faces:
            if face.estimated_age is None or face.id is None:
                continue
            photo_date = self.db.get_photo_date_for_face(face.id)
            if not photo_date:
                continue

            actual_age = photo_date.year - person.birth_year
            error = face.estimated_age - actual_age
            results.append({
                "face_id": face.id,
                "photo_year": photo_date.year,
                "estimated_age": face.estimated_age,
                "actual_age": actual_age,
                "error": error,
            })

        return results

    # ==========================================================================
    # Temporal Bridging
    # ==========================================================================

    def _get_temporal_threshold(self, gap_days: int) -> float:
        """Get similarity threshold based on temporal distance between photos.

        Closer photos in time get lower thresholds since the person's
        appearance changes less over short periods.

        Args:
            gap_days: Number of days between two photos

        Returns:
            Similarity threshold to use
        """
        if gap_days <= 1:
            return self.TEMPORAL_THRESHOLD_SAME_DAY
        elif gap_days <= 30:
            return self.TEMPORAL_THRESHOLD_SAME_MONTH
        elif gap_days <= 365:
            return self.TEMPORAL_THRESHOLD_SAME_YEAR
        else:
            return self.TEMPORAL_THRESHOLD_DIFFERENT_YEARS

    def build_temporal_chain(
        self,
        person_id: int,
        _rebuild: bool = False,
    ) -> TemporalChainResult:
        """Build temporal chain for age progression tracking.

        Links faces through time using relaxed thresholds for
        temporally adjacent photos. Each consecutive pair is classified as
        strong (auto), weak, or a break based on similarity vs threshold.

        Args:
            person_id: Person to build chain for
            _rebuild: Whether to delete existing links and rebuild

        Returns:
            TemporalChainResult with chain statistics
        """
        result = TemporalChainResult(person_id=person_id)

        person = self.db.get_person(person_id)
        if not person:
            return result

        if _rebuild:
            self.db.delete_temporal_links(person_id)

        # Get all faces for person with photo dates
        faces = self.db.get_faces_for_person(person_id)
        if len(faces) < 2:
            return result

        # Collect faces with their photo dates
        face_dates: list[tuple[Face, datetime]] = []
        for face in faces:
            if face.id is None:
                continue
            date = self.db.get_photo_date_for_face(face.id)
            if date:
                face_dates.append((face, date))

        # Sort by date
        face_dates.sort(key=lambda x: x[1])

        if len(face_dates) < 2:
            return result

        # Estimate birth year if person doesn't have one (for gap calculation)
        birth_year = person.birth_year
        if birth_year is None:
            birth_year = self._estimate_birth_year_from_faces(faces)

        # Track years covered for gap calculation
        years_covered: set[int] = set()

        # Build chain by connecting temporally adjacent faces
        for i in range(len(face_dates) - 1):
            face1, date1 = face_dates[i]
            face2, date2 = face_dates[i + 1]

            years_covered.add(date1.year)
            years_covered.add(date2.year)

            if not face1.embedding or not face2.embedding:
                result.breaks += 1
                continue

            # Calculate time gap
            gap_days = abs((date2 - date1).days)
            threshold = self._get_temporal_threshold(gap_days)

            # Compute similarity
            emb1 = self._deserialize_embedding(face1.embedding)
            emb2 = self._deserialize_embedding(face2.embedding)
            similarity = self.compute_similarity(emb1, emb2)

            # Classify the link
            if similarity >= threshold:
                link_type = "auto"
                result.strong_links += 1
            elif similarity >= threshold * 0.7:
                link_type = "weak"
                result.weak_links += 1
            else:
                link_type = "break"
                result.breaks += 1

            # Persist all links (including breaks for visualization)
            if face1.id is not None and face2.id is not None:
                self.db.add_temporal_link(
                    face_id_a=face1.id,
                    face_id_b=face2.id,
                    person_id=person_id,
                    similarity=similarity,
                    temporal_distance_days=gap_days,
                    threshold_used=threshold,
                    link_type=link_type,
                )
                result.total_links += 1

        # Count gap years
        if years_covered:
            min_year = min(years_covered)
            max_year = max(years_covered)
            result.gap_years = (max_year - min_year + 1) - len(years_covered)

        logger.info(
            f"Built temporal chain for person {person_id}: "
            f"{result.total_links} links ({result.strong_links} strong, "
            f"{result.weak_links} weak, {result.breaks} breaks), "
            f"{result.gap_years} gap years"
        )
        return result

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
        threshold: float | None = None,
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
