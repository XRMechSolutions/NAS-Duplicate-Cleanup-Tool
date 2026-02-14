"""Duplicate Comparator for DupliCleaner.

Identifies exact and near-duplicate files by comparing hashes.
Supports perceptual hashing for images to detect visually similar files.
"""

import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import (
    FileRecord,
    MatchType,
)
from duplicleaner.utils.config import get_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Try to import imagehash for perceptual hashing
try:
    import imagehash
    from PIL import Image
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    logger.warning("imagehash not available - near-duplicate detection disabled")


class CompareState(Enum):
    """Current state of the comparator."""

    IDLE = "idle"
    COMPARING = "comparing"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class CompareProgress:
    """Progress information for comparison operation."""

    files_to_compare: int = 0
    files_compared: int = 0
    exact_groups_found: int = 0
    near_groups_found: int = 0
    current_file: str = ""
    start_time: datetime | None = None
    elapsed_seconds: float = 0.0
    state: CompareState = CompareState.IDLE
    errors: int = 0


@dataclass
class CompareResult:
    """Result of a comparison operation."""

    exact_groups: int
    near_groups: int
    total_duplicates: int
    wasted_space: int
    duration_seconds: float


@dataclass
class PerceptualHash:
    """Container for multiple perceptual hash types."""

    phash: str | None = None  # Perceptual hash
    dhash: str | None = None  # Difference hash
    ahash: str | None = None  # Average hash

    def to_string(self) -> str:
        """Combine hashes into a single string for storage."""
        parts = []
        if self.phash:
            parts.append(f"p:{self.phash}")
        if self.dhash:
            parts.append(f"d:{self.dhash}")
        if self.ahash:
            parts.append(f"a:{self.ahash}")
        return "|".join(parts)

    @classmethod
    def from_string(cls, s: str) -> "PerceptualHash":
        """Parse hash string back to PerceptualHash."""
        result = cls()
        if not s:
            return result

        for part in s.split("|"):
            if part.startswith("p:"):
                result.phash = part[2:]
            elif part.startswith("d:"):
                result.dhash = part[2:]
            elif part.startswith("a:"):
                result.ahash = part[2:]

        return result


class Comparator:
    """Finds exact and near-duplicate files."""

    def __init__(
        self,
        db: Database | None = None,
        progress_callback: Callable[[CompareProgress], None] | None = None,
    ):
        """Initialize the comparator.

        Args:
            db: Database instance (uses singleton if not provided)
            progress_callback: Function called with progress updates
        """
        self.db = db or get_database()
        self.config = get_config()
        self.progress_callback = progress_callback

        self._state = CompareState.IDLE
        self._progress = CompareProgress()
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_event = threading.Event()

    @property
    def state(self) -> CompareState:
        """Get current compare state."""
        return self._state

    @property
    def progress(self) -> CompareProgress:
        """Get current progress."""
        return self._progress

    def find_exact_duplicates(self, drive_id: str | None = None) -> int:
        """Find exact duplicates based on content hash.

        Args:
            drive_id: Optional drive ID to limit search

        Returns:
            Number of duplicate groups created
        """
        logger.info("Finding exact duplicates by content hash")

        groups_created = 0

        with self.db.connection() as conn:
            # Find all files with matching content hashes (groups of 2+)
            query = """
                SELECT content_hash, COUNT(*) as cnt
                FROM files
                WHERE content_hash IS NOT NULL
                  AND is_deleted = FALSE
            """
            params = []

            if drive_id:
                query += " AND drive_id = ?"
                params.append(drive_id)

            query += " GROUP BY content_hash HAVING COUNT(*) > 1"

            hash_groups = conn.execute(query, params).fetchall()

            logger.info(f"Found {len(hash_groups)} groups with matching hashes")

            for row in hash_groups:
                content_hash = row["content_hash"]

                # Check for pause/cancel
                self._pause_event.wait()
                if self._cancel_event.is_set():
                    break

                # Get all files with this hash
                file_query = """
                    SELECT id FROM files
                    WHERE content_hash = ?
                      AND is_deleted = FALSE
                """
                file_params = [content_hash]

                if drive_id:
                    file_query += " AND drive_id = ?"
                    file_params.append(drive_id)

                file_rows = conn.execute(file_query, file_params).fetchall()
                file_ids = [r["id"] for r in file_rows]

                if len(file_ids) > 1:
                    # Check if a group already exists for these files
                    existing = self._find_existing_group(file_ids)
                    if not existing:
                        self.db.create_duplicate_group(
                            match_type=MatchType.EXACT,
                            similarity=1.0,
                            file_ids=file_ids,
                        )
                        groups_created += 1
                        self._progress.exact_groups_found += 1

        logger.info(f"Created {groups_created} exact duplicate groups")
        return groups_created

    def find_near_duplicates(
        self,
        drive_id: str | None = None,
        threshold: float | None = None,
    ) -> int:
        """Find near-duplicate images using perceptual hashing.

        Args:
            drive_id: Optional drive ID to limit search
            threshold: Similarity threshold (0.0-1.0), uses config if not provided

        Returns:
            Number of near-duplicate groups created
        """
        if not IMAGEHASH_AVAILABLE:
            logger.warning("imagehash not available, skipping near-duplicate detection")
            return 0

        if threshold is None:
            threshold = self.config.duplicates.near_duplicate_threshold

        logger.info(f"Finding near-duplicate images (threshold: {threshold})")

        # Reset progress
        self._reset_progress()
        self._state = CompareState.COMPARING
        self._progress.state = CompareState.COMPARING
        self._progress.start_time = datetime.now()

        groups_created = 0

        try:
            # Get all image files that need perceptual hashing
            image_files = self._get_image_files(drive_id)
            self._progress.files_to_compare = len(image_files)

            logger.info(f"Found {len(image_files)} images to compare")

            # Compute perceptual hashes for files that don't have them
            for file in image_files:
                self._pause_event.wait()
                if self._cancel_event.is_set():
                    break

                self._progress.current_file = file.path
                self._update_progress()

                if not file.perceptual_hash:
                    phash = self.compute_perceptual_hash(file.path)
                    if phash:
                        hash_str = phash.to_string()
                        self.db.update_file_hash(file.id, perceptual_hash=hash_str)
                        file.perceptual_hash = hash_str

                self._progress.files_compared += 1
                self._update_progress()

            if self._cancel_event.is_set():
                self._state = CompareState.CANCELLED
                return 0

            # Now compare perceptual hashes to find similar images
            groups_created = self._cluster_similar_images(image_files, threshold)

            self._state = CompareState.COMPLETED
            self._progress.state = CompareState.COMPLETED

        except Exception as e:
            logger.error(f"Error finding near duplicates: {e}")
            self._state = CompareState.ERROR
            raise

        # Calculate elapsed time
        if self._progress.start_time:
            self._progress.elapsed_seconds = (
                datetime.now() - self._progress.start_time
            ).total_seconds()

        logger.info(f"Created {groups_created} near-duplicate groups")
        return groups_created

    def compute_perceptual_hash(self, file_path: str) -> PerceptualHash | None:
        """Compute perceptual hashes for an image file.

        Args:
            file_path: Path to image file

        Returns:
            PerceptualHash object or None on error
        """
        if not IMAGEHASH_AVAILABLE:
            return None

        try:
            with Image.open(file_path) as img:
                # Convert to RGB if necessary
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                # Compute multiple hash types
                phash = str(imagehash.phash(img))
                dhash = str(imagehash.dhash(img))
                ahash = str(imagehash.average_hash(img))

                return PerceptualHash(phash=phash, dhash=dhash, ahash=ahash)

        except Exception as e:
            logger.debug(f"Could not compute perceptual hash for {file_path}: {e}")
            self._progress.errors += 1
            return None

    def compare_perceptual_hashes(
        self,
        hash1: PerceptualHash,
        hash2: PerceptualHash,
    ) -> float:
        """Compare two perceptual hashes and return similarity.

        Args:
            hash1: First perceptual hash
            hash2: Second perceptual hash

        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not IMAGEHASH_AVAILABLE:
            return 0.0

        similarities = []

        # Compare pHash
        if hash1.phash and hash2.phash:
            h1 = imagehash.hex_to_hash(hash1.phash)
            h2 = imagehash.hex_to_hash(hash2.phash)
            # Hamming distance - lower is more similar
            distance = h1 - h2
            # Convert to similarity (assuming 64-bit hash)
            similarity = 1 - (distance / 64)
            similarities.append(similarity)

        # Compare dHash
        if hash1.dhash and hash2.dhash:
            h1 = imagehash.hex_to_hash(hash1.dhash)
            h2 = imagehash.hex_to_hash(hash2.dhash)
            distance = h1 - h2
            similarity = 1 - (distance / 64)
            similarities.append(similarity)

        # Compare aHash
        if hash1.ahash and hash2.ahash:
            h1 = imagehash.hex_to_hash(hash1.ahash)
            h2 = imagehash.hex_to_hash(hash2.ahash)
            distance = h1 - h2
            similarity = 1 - (distance / 64)
            similarities.append(similarity)

        # Return average similarity across hash types
        if similarities:
            return sum(similarities) / len(similarities)

        return 0.0

    def extract_video_frame_hashes(self, file_path: str) -> list[dict] | None:
        """Extract keyframes from a video and compute perceptual hashes.

        Args:
            file_path: Path to video file

        Returns:
            List of frame hash dicts or None on error
        """
        if not IMAGEHASH_AVAILABLE:
            return None

        try:
            import cv2
        except ImportError:
            logger.debug("OpenCV not available for video frame extraction")
            return None

        max_frames = self.config.duplicates.video_keyframe_count

        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            logger.debug(f"Could not open video: {file_path}")
            return None

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if fps <= 0 or total_frames <= 0:
                return None

            duration_sec = total_frames / fps

            # Calculate evenly-spaced timestamps
            if duration_sec <= 0:
                return None

            interval = duration_sec / (max_frames + 1)
            timestamps = [interval * (i + 1) for i in range(max_frames)]
            # Clamp to video duration
            timestamps = [t for t in timestamps if t < duration_sec]
            if not timestamps:
                timestamps = [0.0]

            results = []
            for idx, ts in enumerate(timestamps):
                frame_number = int(ts * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Convert BGR -> RGB -> PIL
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                phash_val = str(imagehash.phash(img))
                dhash_val = str(imagehash.dhash(img))

                results.append({
                    "frame_index": idx,
                    "timestamp_sec": ts,
                    "phash": phash_val,
                    "dhash": dhash_val,
                })

            return results if results else None

        except Exception as e:
            logger.debug(f"Error extracting video frames from {file_path}: {e}")
            self._progress.errors += 1
            return None
        finally:
            cap.release()

    def compare_video_frame_hashes(
        self,
        frames_a: list[dict],
        frames_b: list[dict],
    ) -> float:
        """Compare two videos by their frame perceptual hashes.

        For each frame in the shorter video, find the best-matching frame in the
        longer video. Returns the average best-match similarity.

        Args:
            frames_a: Frame hashes for video A
            frames_b: Frame hashes for video B

        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not IMAGEHASH_AVAILABLE or not frames_a or not frames_b:
            return 0.0

        # Use the shorter set as the query set
        if len(frames_a) > len(frames_b):
            frames_a, frames_b = frames_b, frames_a

        best_matches = []
        for fa in frames_a:
            best_sim = 0.0
            ha_p = imagehash.hex_to_hash(fa["phash"]) if fa.get("phash") else None
            ha_d = imagehash.hex_to_hash(fa["dhash"]) if fa.get("dhash") else None

            for fb in frames_b:
                sims = []
                if ha_p and fb.get("phash"):
                    hb_p = imagehash.hex_to_hash(fb["phash"])
                    sims.append(1 - ((ha_p - hb_p) / 64))
                if ha_d and fb.get("dhash"):
                    hb_d = imagehash.hex_to_hash(fb["dhash"])
                    sims.append(1 - ((ha_d - hb_d) / 64))

                if sims:
                    avg = sum(sims) / len(sims)
                    if avg > best_sim:
                        best_sim = avg

            best_matches.append(best_sim)

        return sum(best_matches) / len(best_matches) if best_matches else 0.0

    def find_video_near_duplicates(
        self,
        drive_id: str | None = None,
        threshold: float | None = None,
    ) -> int:
        """Find near-duplicate videos using keyframe perceptual hashing.

        Args:
            drive_id: Optional drive ID to limit search
            threshold: Similarity threshold (0.0-1.0)

        Returns:
            Number of video duplicate groups created
        """
        if not IMAGEHASH_AVAILABLE:
            logger.warning("imagehash not available, skipping video near-duplicate detection")
            return 0

        if not self.config.duplicates.video_near_duplicate:
            logger.info("Video near-duplicate detection disabled in config")
            return 0

        if threshold is None:
            threshold = self.config.duplicates.video_similarity_threshold

        logger.info(f"Finding near-duplicate videos (threshold: {threshold})")

        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv',
                          '.webm', '.m4v', '.mpg', '.mpeg', '.3gp'}

        # Get video files
        with self.db.connection() as conn:
            query = """
                SELECT * FROM files
                WHERE is_deleted = FALSE
                  AND file_type IN ({})
            """.format(','.join('?' * len(video_extensions)))
            params = list(video_extensions)
            if drive_id:
                query += " AND drive_id = ?"
                params.append(drive_id)
            rows = conn.execute(query, params).fetchall()
            video_files = [FileRecord(**dict(row)) for row in rows]

        if len(video_files) < 2:
            logger.info("Less than 2 video files, skipping video comparison")
            return 0

        logger.info(f"Found {len(video_files)} videos to compare")

        # Get already-processed file IDs
        processed_ids = set(self.db.get_files_with_video_frames(drive_id))

        # Extract and store frame hashes for unprocessed videos
        for vf in video_files:
            self._pause_event.wait()
            if self._cancel_event.is_set():
                break

            self._progress.current_file = vf.path
            self._update_progress()

            if vf.id not in processed_ids:
                frame_hashes = self.extract_video_frame_hashes(vf.path)
                if frame_hashes:
                    self.db.store_video_frame_hashes(vf.id, frame_hashes)
                    processed_ids.add(vf.id)

        if self._cancel_event.is_set():
            return 0

        # Load all frame hashes for comparison
        video_hashes: dict[int, list[dict]] = {}
        for vf in video_files:
            if vf.id in processed_ids:
                frames = self.db.get_video_frame_hashes(vf.id)
                if frames:
                    video_hashes[vf.id] = frames

        if len(video_hashes) < 2:
            return 0

        # Compare all video pairs
        video_ids = list(video_hashes.keys())
        similar_pairs: list[tuple[int, int, float]] = []

        total_comparisons = len(video_ids) * (len(video_ids) - 1) // 2
        logger.info(f"Comparing {total_comparisons} video pairs")

        for i, id1 in enumerate(video_ids):
            if self._cancel_event.is_set():
                break

            for id2 in video_ids[i + 1:]:
                similarity = self.compare_video_frame_hashes(
                    video_hashes[id1], video_hashes[id2]
                )
                if similarity >= threshold:
                    similar_pairs.append((id1, id2, similarity))

        logger.info(f"Found {len(similar_pairs)} similar video pairs")

        # Cluster and create groups
        groups = self._union_find_cluster(similar_pairs)
        groups_created = 0
        for group_file_ids in groups.values():
            if len(group_file_ids) > 1:
                avg_similarity = self._calculate_group_similarity(group_file_ids, similar_pairs)
                existing = self._find_existing_group(list(group_file_ids))
                if not existing:
                    self.db.create_duplicate_group(
                        match_type=MatchType.NEAR,
                        similarity=avg_similarity,
                        file_ids=list(group_file_ids),
                    )
                    groups_created += 1
                    self._progress.near_groups_found += 1

        logger.info(f"Created {groups_created} video near-duplicate groups")
        return groups_created

    def find_document_near_duplicates(
        self,
        drive_id: str | None = None,
        threshold: float = 0.95,
    ) -> int:
        """Find near-duplicate documents by comparing extracted text.

        Matches documents across formats (e.g., .docx and .pdf of same content).

        Args:
            drive_id: Optional drive ID to limit search
            threshold: Text similarity threshold (0.0-1.0)

        Returns:
            Number of document duplicate groups created
        """
        document_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx',
                              '.ppt', '.pptx', '.txt', '.rtf', '.odt'}

        # Get document files that have OCR/text extracted
        with self.db.connection() as conn:
            query = """
                SELECT f.id, f.path, f.filename, f.file_type, o.extracted_text
                FROM files f
                JOIN ocr_results o ON o.file_id = f.id
                WHERE f.is_deleted = FALSE
                  AND f.file_type IN ({})
                  AND o.extracted_text IS NOT NULL
                  AND LENGTH(o.extracted_text) > 50
            """.format(','.join('?' * len(document_extensions)))
            params = list(document_extensions)
            if drive_id:
                query += " AND f.drive_id = ?"
                params.append(drive_id)
            rows = conn.execute(query, params).fetchall()

        if len(rows) < 2:
            logger.info("Less than 2 documents with text, skipping document comparison")
            return 0

        logger.info(f"Comparing {len(rows)} documents by text content")

        # Build text fingerprints (normalized, first 5000 chars for efficiency)
        doc_texts: dict[int, str] = {}
        for row in rows:
            text = row["extracted_text"].strip().lower()
            # Normalize whitespace
            text = " ".join(text.split())
            doc_texts[row["id"]] = text[:5000]

        # Compare document pairs by text similarity
        doc_ids = list(doc_texts.keys())
        similar_pairs: list[tuple[int, int, float]] = []

        for i, id1 in enumerate(doc_ids):
            if self._cancel_event.is_set():
                break
            text1 = doc_texts[id1]
            for id2 in doc_ids[i + 1:]:
                text2 = doc_texts[id2]
                similarity = self._text_similarity(text1, text2)
                if similarity >= threshold:
                    similar_pairs.append((id1, id2, similarity))

        logger.info(f"Found {len(similar_pairs)} similar document pairs")

        # Cluster and create groups
        groups = self._union_find_cluster(similar_pairs)
        groups_created = 0
        for group_file_ids in groups.values():
            if len(group_file_ids) > 1:
                avg_similarity = self._calculate_group_similarity(group_file_ids, similar_pairs)
                existing = self._find_existing_group(list(group_file_ids))
                if not existing:
                    self.db.create_duplicate_group(
                        match_type=MatchType.NEAR,
                        similarity=avg_similarity,
                        file_ids=list(group_file_ids),
                    )
                    groups_created += 1
                    self._progress.near_groups_found += 1

        logger.info(f"Created {groups_created} document near-duplicate groups")
        return groups_created

    @staticmethod
    def _text_similarity(text1: str, text2: str) -> float:
        """Compute similarity between two text strings using character bigrams.

        Uses Jaccard similarity on character bigrams for speed.
        """
        if not text1 or not text2:
            return 0.0
        if text1 == text2:
            return 1.0

        # Use character bigrams for fuzzy matching
        def bigrams(s: str) -> set[str]:
            return {s[i:i+2] for i in range(len(s) - 1)} if len(s) > 1 else {s}

        bg1 = bigrams(text1)
        bg2 = bigrams(text2)
        intersection = len(bg1 & bg2)
        union = len(bg1 | bg2)
        return intersection / union if union > 0 else 0.0

    def find_all_duplicates(self, drive_id: str | None = None) -> CompareResult:
        """Find both exact and near duplicates.

        Args:
            drive_id: Optional drive ID to limit search

        Returns:
            CompareResult with statistics
        """
        logger.info("Starting full duplicate detection")

        self._reset_progress()
        self._state = CompareState.COMPARING
        self._progress.state = CompareState.COMPARING
        self._progress.start_time = datetime.now()
        self._cancel_event.clear()
        self._pause_event.set()

        try:
            # Find exact duplicates first
            self.find_exact_duplicates(drive_id)

            if not self._cancel_event.is_set():
                # Find near duplicates (images)
                self.find_near_duplicates(drive_id)

            if not self._cancel_event.is_set():
                # Find near duplicates (videos)
                self.find_video_near_duplicates(drive_id)

            if not self._cancel_event.is_set():
                # Find near duplicates (documents by text content)
                self.find_document_near_duplicates(drive_id)

            # Calculate statistics
            stats = self._calculate_stats()

            if not self._cancel_event.is_set():
                self._state = CompareState.COMPLETED
                self._progress.state = CompareState.COMPLETED

        except Exception as e:
            logger.error(f"Error during duplicate detection: {e}")
            self._state = CompareState.ERROR
            self._progress.state = CompareState.ERROR
            raise

        if self._progress.start_time:
            self._progress.elapsed_seconds = (
                datetime.now() - self._progress.start_time
            ).total_seconds()

        return CompareResult(
            exact_groups=self._progress.exact_groups_found,
            near_groups=self._progress.near_groups_found,
            total_duplicates=stats["total_duplicates"],
            wasted_space=stats["wasted_space"],
            duration_seconds=self._progress.elapsed_seconds,
        )

    def _get_image_files(self, drive_id: str | None = None) -> list[FileRecord]:
        """Get all image files from the database.

        Args:
            drive_id: Optional drive ID to filter

        Returns:
            List of FileRecord objects
        """
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
                          '.tif', '.webp', '.heic', '.heif'}

        with self.db.connection() as conn:
            query = """
                SELECT * FROM files
                WHERE is_deleted = FALSE
                  AND file_type IN ({})
            """.format(','.join('?' * len(image_extensions)))

            params = list(image_extensions)

            if drive_id:
                query += " AND drive_id = ?"
                params.append(drive_id)

            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def _cluster_similar_images(
        self,
        files: list[FileRecord],
        threshold: float,
    ) -> int:
        """Cluster similar images into duplicate groups.

        Uses a simple O(n^2) comparison for now. For large collections,
        this should be optimized with LSH or similar techniques.

        Args:
            files: List of files with perceptual hashes
            threshold: Similarity threshold

        Returns:
            Number of groups created
        """
        # Build hash lookup
        hash_lookup: dict[int, PerceptualHash] = {}
        for file in files:
            if file.perceptual_hash and file.id:
                hash_lookup[file.id] = PerceptualHash.from_string(file.perceptual_hash)

        # Find similar pairs
        similar_pairs: list[tuple[int, int, float]] = []

        file_ids = list(hash_lookup.keys())
        total_comparisons = len(file_ids) * (len(file_ids) - 1) // 2

        logger.info(f"Comparing {total_comparisons} image pairs")

        comparisons_done = 0
        for i, id1 in enumerate(file_ids):
            if self._cancel_event.is_set():
                break

            hash1 = hash_lookup[id1]

            for id2 in file_ids[i + 1:]:
                hash2 = hash_lookup[id2]

                similarity = self.compare_perceptual_hashes(hash1, hash2)

                if similarity >= threshold:
                    similar_pairs.append((id1, id2, similarity))

                comparisons_done += 1

                # Update progress periodically
                if comparisons_done % 10000 == 0:
                    logger.debug(f"Compared {comparisons_done}/{total_comparisons} pairs")

        logger.info(f"Found {len(similar_pairs)} similar pairs")

        # Cluster similar pairs into groups using union-find
        groups = self._union_find_cluster(similar_pairs)

        # Create database groups
        groups_created = 0
        for group_file_ids in groups.values():
            if len(group_file_ids) > 1:
                # Calculate average similarity for the group
                avg_similarity = self._calculate_group_similarity(
                    group_file_ids, similar_pairs
                )

                # Check if group already exists
                existing = self._find_existing_group(list(group_file_ids))
                if not existing:
                    self.db.create_duplicate_group(
                        match_type=MatchType.NEAR,
                        similarity=avg_similarity,
                        file_ids=list(group_file_ids),
                    )
                    groups_created += 1
                    self._progress.near_groups_found += 1

        return groups_created

    def _union_find_cluster(
        self,
        pairs: list[tuple[int, int, float]],
    ) -> dict[int, set[int]]:
        """Cluster items using union-find algorithm.

        Args:
            pairs: List of (id1, id2, similarity) tuples

        Returns:
            Dict mapping root ID to set of member IDs
        """
        parent: dict[int, int] = {}

        def find(x: int) -> int:
            if x not in parent:
                parent[x] = x
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union all similar pairs
        for id1, id2, _ in pairs:
            union(id1, id2)

        # Group by root
        groups: dict[int, set[int]] = defaultdict(set)
        for item in parent:
            root = find(item)
            groups[root].add(item)

        return groups

    def _calculate_group_similarity(
        self,
        file_ids: set[int],
        pairs: list[tuple[int, int, float]],
    ) -> float:
        """Calculate average similarity within a group.

        Args:
            file_ids: Set of file IDs in the group
            pairs: All similar pairs

        Returns:
            Average similarity
        """
        relevant_similarities = [
            sim for id1, id2, sim in pairs
            if id1 in file_ids and id2 in file_ids
        ]

        if relevant_similarities:
            return sum(relevant_similarities) / len(relevant_similarities)

        return 0.9  # Default if no pairs found

    def _find_existing_group(self, file_ids: list[int]) -> int | None:
        """Check if a duplicate group already exists for these files.

        Args:
            file_ids: List of file IDs

        Returns:
            Group ID if exists, None otherwise
        """
        if not file_ids:
            return None

        with self.db.connection() as conn:
            # Check if all these files are already in a group together
            placeholders = ','.join('?' * len(file_ids))
            query = f"""
                SELECT group_id, COUNT(*) as cnt
                FROM duplicate_members
                WHERE file_id IN ({placeholders})
                GROUP BY group_id
                HAVING COUNT(*) = ?
            """
            row = conn.execute(query, file_ids + [len(file_ids)]).fetchone()

            if row:
                return row["group_id"]

        return None

    def _calculate_stats(self) -> dict:
        """Calculate duplicate statistics.

        Returns:
            Dict with total_duplicates and wasted_space
        """
        stats = self.db.get_statistics()
        return {
            "total_duplicates": stats.get("pending_duplicate_groups", 0),
            "wasted_space": stats.get("wasted_space", 0),
        }

    def pause(self) -> None:
        """Pause the comparison operation."""
        if self._state == CompareState.COMPARING:
            self._pause_event.clear()
            self._state = CompareState.PAUSED
            self._progress.state = CompareState.PAUSED
            logger.info("Comparison paused")

    def resume(self) -> None:
        """Resume a paused comparison."""
        if self._state == CompareState.PAUSED:
            self._pause_event.set()
            self._state = CompareState.COMPARING
            self._progress.state = CompareState.COMPARING
            logger.info("Comparison resumed")

    def cancel(self) -> None:
        """Cancel the comparison operation."""
        self._cancel_event.set()
        self._pause_event.set()
        logger.info("Comparison cancellation requested")

    def _reset_progress(self) -> None:
        """Reset progress counters."""
        self._progress = CompareProgress()

    def _update_progress(self) -> None:
        """Update progress and call callback."""
        if self._progress.start_time:
            elapsed = (datetime.now() - self._progress.start_time).total_seconds()
            self._progress.elapsed_seconds = elapsed

        if self.progress_callback:
            self.progress_callback(self._progress)


def compute_image_hash(file_path: str, hash_type: str = "phash") -> str | None:
    """Convenience function to compute a single image hash.

    Args:
        file_path: Path to image file
        hash_type: Type of hash (phash, dhash, ahash)

    Returns:
        Hash string or None on error
    """
    if not IMAGEHASH_AVAILABLE:
        return None

    try:
        with Image.open(file_path) as img:
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            if hash_type == "phash":
                return str(imagehash.phash(img))
            elif hash_type == "dhash":
                return str(imagehash.dhash(img))
            elif hash_type == "ahash":
                return str(imagehash.average_hash(img))
            else:
                return str(imagehash.phash(img))

    except Exception as e:
        logger.debug(f"Could not compute {hash_type} for {file_path}: {e}")
        return None
