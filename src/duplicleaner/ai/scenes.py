"""Scene classification and semantic search module.

Uses CLIP (Contrastive Language-Image Pre-training) for zero-shot
scene classification and semantic search encoding.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from threading import Event
from typing import Callable, Optional

import numpy as np

from ..db.database import Database
from ..db.models import FileRecord, SceneAnalysis
from ..utils.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import CLIP libraries
CLIP_AVAILABLE = False
TORCH_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    logger.warning("PyTorch not available.")

try:
    import open_clip
    CLIP_AVAILABLE = True
except ImportError:
    logger.warning("open-clip-torch not available. Scene classification disabled.")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow not available.")


# Default scene categories
DEFAULT_CATEGORIES = [
    "beach",
    "mountain",
    "forest",
    "city",
    "indoor",
    "restaurant",
    "party",
    "wedding",
    "birthday",
    "sports",
    "travel",
    "nature",
    "portrait",
    "group photo",
    "document",
    "screenshot",
    "food",
    "pet",
    "vehicle",
    "art",
    "sunset",
    "night",
    "water",
    "snow",
    "garden",
]


@dataclass
class SceneResult:
    """Result of scene classification for an image."""
    file_id: int
    categories: dict[str, float]  # category -> confidence
    top_category: str
    top_confidence: float
    embedding: Optional[np.ndarray] = None


@dataclass
class SearchResult:
    """Result of semantic search."""
    file_id: int
    file_path: str
    similarity: float
    preview_categories: dict[str, float]


@dataclass
class SceneAnalysisProgress:
    """Progress tracking for scene analysis."""
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


class SceneClassifier:
    """Scene classification and semantic search using CLIP."""

    # Model configuration
    DEFAULT_MODEL = "ViT-L-14"
    DEFAULT_PRETRAINED = "openai"

    # Embedding dimensions (varies by model)
    EMBEDDING_DIM = 768  # For ViT-L-14

    def __init__(
        self,
        db: Database,
        model_name: str = DEFAULT_MODEL,
        pretrained: str = DEFAULT_PRETRAINED,
        use_gpu: bool = True,
        categories: Optional[list[str]] = None,
    ):
        """Initialize scene classifier.

        Args:
            db: Database instance
            model_name: CLIP model name
            pretrained: Pretrained weights source
            use_gpu: Whether to use GPU
            categories: Custom categories (uses defaults if None)
        """
        self.db = db
        self.model_name = model_name
        self.pretrained = pretrained
        self.use_gpu = use_gpu
        self.categories = categories or DEFAULT_CATEGORIES.copy()

        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device = None
        self._model_loaded = False

        # Cached text embeddings for categories
        self._category_embeddings: Optional[torch.Tensor] = None

        # Progress tracking
        self.progress = SceneAnalysisProgress()
        self._cancel_event = Event()
        self._progress_callback: Optional[Callable[[SceneAnalysisProgress], None]] = None

    def set_progress_callback(
        self, callback: Optional[Callable[[SceneAnalysisProgress], None]]
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
        """Check if CLIP is available."""
        return CLIP_AVAILABLE and TORCH_AVAILABLE and PIL_AVAILABLE

    def load_model(self) -> bool:
        """Load the CLIP model.

        Returns:
            True if model loaded successfully
        """
        if not self.is_available():
            logger.error("CLIP dependencies not available")
            return False

        if self._model_loaded:
            return True

        try:
            self.progress.phase = "loading_model"
            self._notify_progress()

            # Determine device
            if self.use_gpu and torch.cuda.is_available():
                self._device = torch.device("cuda")
            else:
                self._device = torch.device("cpu")

            logger.info(f"Loading CLIP model {self.model_name} on {self._device}")

            # Load model
            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained,
                device=self._device,
            )
            self._tokenizer = open_clip.get_tokenizer(self.model_name)

            self._model.eval()
            self._model_loaded = True

            # Pre-compute category embeddings
            self._compute_category_embeddings()

            logger.info(f"CLIP model loaded: {self.model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            self._model = None
            self._model_loaded = False
            return False

    def unload_model(self) -> None:
        """Unload model to free memory."""
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._category_embeddings = None
        self._model_loaded = False

        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.empty_cache()

        logger.info("CLIP model unloaded")

    def _compute_category_embeddings(self) -> None:
        """Pre-compute text embeddings for all categories."""
        if not self._model_loaded:
            return

        # Create text prompts
        prompts = [f"a photo of {cat}" for cat in self.categories]

        with torch.no_grad():
            text_tokens = self._tokenizer(prompts).to(self._device)
            self._category_embeddings = self._model.encode_text(text_tokens)
            self._category_embeddings = self._category_embeddings / self._category_embeddings.norm(
                dim=-1, keepdim=True
            )

    def add_custom_category(self, category: str) -> None:
        """Add a custom category.

        Args:
            category: Category name to add
        """
        if category not in self.categories:
            self.categories.append(category)
            # Recompute embeddings
            if self._model_loaded:
                self._compute_category_embeddings()

    def remove_category(self, category: str) -> None:
        """Remove a category.

        Args:
            category: Category name to remove
        """
        if category in self.categories:
            self.categories.remove(category)
            if self._model_loaded:
                self._compute_category_embeddings()

    # ==========================================================================
    # Image Analysis
    # ==========================================================================

    def encode_image(self, image_path: str) -> Optional[np.ndarray]:
        """Encode an image to CLIP embedding.

        Args:
            image_path: Path to image file

        Returns:
            Normalized embedding vector or None
        """
        if not self._model_loaded:
            if not self.load_model():
                return None

        try:
            # Load and preprocess image
            image = Image.open(image_path).convert("RGB")
            image_input = self._preprocess(image).unsqueeze(0).to(self._device)

            # Encode
            with torch.no_grad():
                image_embedding = self._model.encode_image(image_input)
                image_embedding = image_embedding / image_embedding.norm(dim=-1, keepdim=True)

            return image_embedding.cpu().numpy().flatten()

        except Exception as e:
            logger.error(f"Error encoding image {image_path}: {e}")
            return None

    def classify_image(
        self,
        image_path: str,
        top_k: int = 5,
    ) -> Optional[SceneResult]:
        """Classify an image into scene categories.

        Args:
            image_path: Path to image file
            top_k: Number of top categories to return

        Returns:
            SceneResult or None on error
        """
        if not self._model_loaded:
            if not self.load_model():
                return None

        try:
            # Encode image
            image = Image.open(image_path).convert("RGB")
            image_input = self._preprocess(image).unsqueeze(0).to(self._device)

            with torch.no_grad():
                image_embedding = self._model.encode_image(image_input)
                image_embedding = image_embedding / image_embedding.norm(dim=-1, keepdim=True)

                # Compute similarity with categories
                similarities = (image_embedding @ self._category_embeddings.T).squeeze()
                similarities = similarities.cpu().numpy()

            # Get top categories
            top_indices = np.argsort(similarities)[::-1][:top_k]
            categories = {}
            for idx in top_indices:
                cat = self.categories[idx]
                conf = float(similarities[idx])
                # Convert to probability-like score (0-1)
                categories[cat] = max(0.0, min(1.0, (conf + 1) / 2))

            top_category = self.categories[top_indices[0]]
            top_confidence = categories[top_category]

            return SceneResult(
                file_id=0,  # Will be set by caller
                categories=categories,
                top_category=top_category,
                top_confidence=top_confidence,
                embedding=image_embedding.cpu().numpy().flatten(),
            )

        except Exception as e:
            logger.error(f"Error classifying {image_path}: {e}")
            return None

    def analyze_file(self, file_record: FileRecord) -> Optional[SceneAnalysis]:
        """Analyze a file and store results.

        Args:
            file_record: FileRecord to analyze

        Returns:
            SceneAnalysis object or None
        """
        if file_record.id is None:
            return None

        result = self.classify_image(file_record.path)
        if not result:
            return None

        # Create SceneAnalysis
        analysis = SceneAnalysis(
            file_id=file_record.id,
            categories=json.dumps(result.categories),
            clip_embedding=result.embedding.tobytes() if result.embedding is not None else None,
            analyzed_at=datetime.now(),
        )

        # Store in database
        self.db.add_scene_analysis(analysis)

        return analysis

    def analyze_batch(
        self,
        file_records: list[FileRecord],
        skip_existing: bool = True,
    ) -> int:
        """Analyze a batch of files.

        Args:
            file_records: Files to analyze
            skip_existing: Skip files with existing analysis

        Returns:
            Number of files analyzed
        """
        self.progress = SceneAnalysisProgress(
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
                if existing:
                    continue

            # Analyze
            result = self.analyze_file(file_record)
            if result:
                analyzed += 1

        self.progress.phase = "complete"
        self._notify_progress()

        return analyzed

    # ==========================================================================
    # Semantic Search
    # ==========================================================================

    def encode_text(self, text: str) -> Optional[np.ndarray]:
        """Encode text query to CLIP embedding.

        Args:
            text: Text query

        Returns:
            Normalized embedding or None
        """
        if not self._model_loaded:
            if not self.load_model():
                return None

        try:
            with torch.no_grad():
                text_tokens = self._tokenizer([text]).to(self._device)
                text_embedding = self._model.encode_text(text_tokens)
                text_embedding = text_embedding / text_embedding.norm(dim=-1, keepdim=True)

            return text_embedding.cpu().numpy().flatten()

        except Exception as e:
            logger.error(f"Error encoding text '{text}': {e}")
            return None

    def search(
        self,
        query: str,
        limit: int = 50,
        threshold: float = 0.2,
    ) -> list[SearchResult]:
        """Search images by text query.

        Args:
            query: Natural language search query
            limit: Maximum results
            threshold: Minimum similarity threshold

        Returns:
            List of SearchResult objects
        """
        # Encode query
        query_embedding = self.encode_text(query)
        if query_embedding is None:
            return []

        # Get all scene analyses with embeddings
        analyses = self.db.get_all_scene_analyses_with_embeddings()

        results = []
        for file_id, embedding_bytes, categories_json in analyses:
            if embedding_bytes is None:
                continue

            # Deserialize embedding
            image_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)

            # Compute similarity
            similarity = float(np.dot(query_embedding, image_embedding))

            if similarity >= threshold:
                # Get file path
                file_record = self.db.get_file(file_id)
                if not file_record:
                    continue

                # Parse categories
                categories = json.loads(categories_json) if categories_json else {}

                results.append(SearchResult(
                    file_id=file_id,
                    file_path=file_record.path,
                    similarity=similarity,
                    preview_categories=categories,
                ))

        # Sort by similarity
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]

    def find_similar_images(
        self,
        file_id: int,
        limit: int = 20,
        threshold: float = 0.7,
    ) -> list[SearchResult]:
        """Find images visually similar to a given image.

        Args:
            file_id: Source image file ID
            limit: Maximum results
            threshold: Minimum similarity

        Returns:
            List of SearchResult objects
        """
        # Get source embedding
        source = self.db.get_scene_analysis(file_id)
        if not source or not source.clip_embedding:
            return []

        source_embedding = np.frombuffer(source.clip_embedding, dtype=np.float32)

        # Get all other analyses
        analyses = self.db.get_all_scene_analyses_with_embeddings()

        results = []
        for other_id, embedding_bytes, categories_json in analyses:
            if other_id == file_id or embedding_bytes is None:
                continue

            other_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
            similarity = float(np.dot(source_embedding, other_embedding))

            if similarity >= threshold:
                file_record = self.db.get_file(other_id)
                if not file_record:
                    continue

                categories = json.loads(categories_json) if categories_json else {}

                results.append(SearchResult(
                    file_id=other_id,
                    file_path=file_record.path,
                    similarity=similarity,
                    preview_categories=categories,
                ))

        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]

    def cancel(self) -> None:
        """Cancel ongoing operation."""
        self._cancel_event.set()
        logger.info("Scene analysis cancelled")
