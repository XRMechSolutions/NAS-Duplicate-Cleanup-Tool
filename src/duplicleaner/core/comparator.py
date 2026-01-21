"""Duplicate Comparator for DupliCleaner.

Identifies exact and near-duplicate files by comparing hashes.
Supports perceptual hashing for images to detect visually similar files.
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import (
    FileRecord,
    DuplicateGroup,
    DuplicateMember,
    MatchType,
    GroupStatus,
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
    start_time: Optional[datetime] = None
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

    phash: Optional[str] = None  # Perceptual hash
    dhash: Optional[str] = None  # Difference hash
    ahash: Optional[str] = None  # Average hash

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
        db: Optional[Database] = None,
        progress_callback: Optional[Callable[[CompareProgress], None]] = None,
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

    def find_exact_duplicates(self, drive_id: Optional[str] = None) -> int:
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
        drive_id: Optional[str] = None,
        threshold: Optional[float] = None,
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

    def compute_perceptual_hash(self, file_path: str) -> Optional[PerceptualHash]:
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

    def find_all_duplicates(self, drive_id: Optional[str] = None) -> CompareResult:
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
            exact_groups = self.find_exact_duplicates(drive_id)

            if not self._cancel_event.is_set():
                # Find near duplicates
                near_groups = self.find_near_duplicates(drive_id)
            else:
                near_groups = 0

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

    def _get_image_files(self, drive_id: Optional[str] = None) -> list[FileRecord]:
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

    def _find_existing_group(self, file_ids: list[int]) -> Optional[int]:
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


def compute_image_hash(file_path: str, hash_type: str = "phash") -> Optional[str]:
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
