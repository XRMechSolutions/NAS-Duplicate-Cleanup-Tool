"""JPEG fragment separator - extract distinct photos from mixed corrupt files."""

import io
from pathlib import Path

import numpy as np
from PIL import Image

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class PhotoFragment:
    """Represents a photo fragment extracted from corrupt file."""

    def __init__(self, offset: int, image: Image.Image, segment_data: bytes):
        """Initialize photo fragment.

        Args:
            offset: Byte offset in original file
            image: Decoded PIL image
            segment_data: Raw JPEG bytes
        """
        self.offset = offset
        self.image = image
        self.segment_data = segment_data
        self.size = image.size
        self.pixel_count = image.size[0] * image.size[1]

        # Extract features for similarity comparison
        self.features = self._extract_features()

    def _extract_features(self) -> dict:
        """Extract visual features from image for comparison."""
        img_array = np.array(self.image)

        # Calculate histogram
        if len(img_array.shape) == 3:
            hist_r = np.histogram(img_array[:, :, 0], bins=32, range=(0, 255))[0]
            hist_g = np.histogram(img_array[:, :, 1], bins=32, range=(0, 255))[0]
            hist_b = np.histogram(img_array[:, :, 2], bins=32, range=(0, 255))[0]
            histogram = np.concatenate([hist_r, hist_g, hist_b])

            # Average color
            avg_color = np.mean(img_array, axis=(0, 1))

            # Check for gray pixels (missing data)
            gray_mask = np.all(img_array == 128, axis=2)
            gray_percentage = np.sum(gray_mask) / self.pixel_count * 100

        else:
            histogram = np.histogram(img_array, bins=32, range=(0, 255))[0]
            avg_color = np.array([np.mean(img_array)])
            gray_percentage = np.sum(img_array == 128) / self.pixel_count * 100

        # Average brightness
        brightness = np.mean(img_array)

        return {
            'histogram': histogram,
            'avg_color': avg_color,
            'brightness': brightness,
            'gray_percentage': gray_percentage,
            'aspect_ratio': self.size[0] / self.size[1] if self.size[1] > 0 else 0
        }

    def similarity_to(self, other: 'PhotoFragment') -> float:
        """Calculate similarity score to another fragment (0-1, higher = more similar).

        Args:
            other: Another photo fragment

        Returns:
            Similarity score
        """
        # Histogram similarity (cosine similarity)
        hist1 = self.features['histogram']
        hist2 = other.features['histogram']

        # Handle different histogram sizes (RGB vs grayscale)
        if len(hist1) != len(hist2):
            # Can't compare directly, use color similarity instead
            hist_sim = 0.5
        else:
            hist_sim = np.dot(hist1, hist2) / (np.linalg.norm(hist1) * np.linalg.norm(hist2) + 1e-10)

        # Color similarity
        color_dist = np.linalg.norm(self.features['avg_color'] - other.features['avg_color'])
        color_sim = 1 / (1 + color_dist / 255)

        # Brightness similarity
        bright_diff = abs(self.features['brightness'] - other.features['brightness'])
        bright_sim = 1 / (1 + bright_diff / 255)

        # Aspect ratio similarity
        aspect_diff = abs(self.features['aspect_ratio'] - other.features['aspect_ratio'])
        aspect_sim = 1 / (1 + aspect_diff)

        # Gray percentage similarity (fragments from same photo should have similar corruption)
        gray_diff = abs(self.features['gray_percentage'] - other.features['gray_percentage'])
        gray_sim = 1 / (1 + gray_diff / 100)

        # Weighted average
        similarity = (
            0.4 * hist_sim +
            0.2 * color_sim +
            0.2 * bright_sim +
            0.1 * aspect_sim +
            0.1 * gray_sim
        )

        return similarity


class JPEGFragmentSeparator:
    """Separate and extract distinct photos from mixed corrupt JPEG files."""

    def __init__(self, similarity_threshold: float = 0.7):
        """Initialize fragment separator.

        Args:
            similarity_threshold: Threshold for grouping similar fragments (0-1)
        """
        self.similarity_threshold = similarity_threshold

    def extract_all_fragments(self, file_path: str) -> list[PhotoFragment]:
        """Extract all decodable photo fragments from file.

        Args:
            file_path: Path to corrupt JPEG file

        Returns:
            List of photo fragments
        """
        logger.info(f"Extracting fragments from: {file_path}")

        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            # Find all SOI markers
            soi_positions = []
            for i in range(len(data) - 1):
                if data[i] == 0xFF and data[i+1] == 0xD8:
                    soi_positions.append(i)

            logger.info(f"Found {len(soi_positions)} potential image starts")

            fragments = []

            # Try to decode from each SOI position
            for soi_pos in soi_positions:
                segment = data[soi_pos:]

                try:
                    # Try to decode
                    img = Image.open(io.BytesIO(segment))
                    img.load()

                    # Skip if too small (probably corrupt data), BUT keep if reasonably sized
                    # Changed from 50 to allow smaller fragments
                    if img.size[0] < 32 or img.size[1] < 32:
                        continue

                    # Skip duplicates at nearby offsets (within 1KB) with same size
                    is_duplicate = False
                    for existing in fragments:
                        if abs(existing.offset - soi_pos) < 1024 and existing.size == img.size:
                            is_duplicate = True
                            break

                    if is_duplicate:
                        continue

                    # Check if it has actual image data (not all gray)
                    img_array = np.array(img)
                    if len(img_array.shape) == 3:
                        non_gray = np.sum(~np.all(img_array == 128, axis=2))
                    else:
                        non_gray = np.sum(img_array != 128)

                    data_percentage = non_gray / (img.size[0] * img.size[1]) * 100

                    # Keep if has at least 5% actual data (lowered threshold to catch more)
                    if data_percentage > 5:
                        fragment = PhotoFragment(soi_pos, img.copy(), segment[:100000])
                        fragments.append(fragment)
                        logger.info(f"  Fragment at {soi_pos}: {img.size[0]}x{img.size[1]}, {data_percentage:.1f}% data")

                except Exception:
                    continue

            logger.info(f"Extracted {len(fragments)} valid fragments")
            return fragments

        except Exception as e:
            logger.error(f"Failed to extract fragments: {e}")
            return []

    def group_similar_fragments(self, fragments: list[PhotoFragment]) -> list[list[PhotoFragment]]:
        """Group similar fragments together (same photo).

        Args:
            fragments: List of photo fragments

        Returns:
            List of fragment groups
        """
        if not fragments:
            return []

        logger.info(f"Grouping {len(fragments)} fragments by similarity...")

        # Start with each fragment in its own group
        groups = [[f] for f in fragments]

        # Iteratively merge similar groups
        merged = True
        while merged:
            merged = False

            for i in range(len(groups)):
                if merged:
                    break

                for j in range(i + 1, len(groups)):
                    # Compare representative fragments from each group
                    frag1 = groups[i][0]
                    frag2 = groups[j][0]

                    similarity = frag1.similarity_to(frag2)

                    if similarity > self.similarity_threshold:
                        # Merge groups
                        logger.info(f"  Merging groups (similarity: {similarity:.2f})")
                        groups[i].extend(groups[j])
                        groups.pop(j)
                        merged = True
                        break

        # Sort fragments within each group by pixel count (largest first)
        for group in groups:
            group.sort(key=lambda f: f.pixel_count, reverse=True)

        logger.info(f"Found {len(groups)} distinct photos")
        return groups

    def separate_photos(self, file_path: str, output_dir: str, base_name: str) -> list[str]:
        """Separate and save distinct photos from mixed corrupt file.

        Args:
            file_path: Path to corrupt JPEG file
            output_dir: Directory to save separated photos
            base_name: Base name for output files

        Returns:
            List of paths to saved photos
        """
        logger.info(f"Separating photos from: {file_path}")

        # Extract all fragments
        fragments = self.extract_all_fragments(file_path)

        if not fragments:
            logger.warning("No fragments could be extracted")
            return []

        # Group similar fragments
        groups = self.group_similar_fragments(fragments)

        # Save best fragment from each group
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = []

        for i, group in enumerate(groups, 1):
            # Use largest fragment from group
            best_fragment = group[0]

            # Generate filename
            output_name = f"{base_name}_photo{i}_{best_fragment.size[0]}x{best_fragment.size[1]}.jpg"
            output_path = output_dir / output_name

            # Save
            best_fragment.image.save(output_path, 'JPEG', quality=95)
            saved_paths.append(str(output_path))

            logger.info(f"  Photo {i}: {best_fragment.size[0]}x{best_fragment.size[1]} "
                       f"({best_fragment.features['gray_percentage']:.1f}% missing) "
                       f"-> {output_name}")

        return saved_paths


def separate_jpeg_fragments(input_path: str, output_dir: str, similarity_threshold: float = 0.7) -> list[str]:
    """Convenience function to separate JPEG fragments.

    Args:
        input_path: Path to corrupt JPEG file
        output_dir: Directory to save separated photos
        similarity_threshold: Threshold for grouping similar fragments

    Returns:
        List of paths to saved photos
    """
    separator = JPEGFragmentSeparator(similarity_threshold)
    base_name = Path(input_path).stem
    return separator.separate_photos(input_path, output_dir, base_name)
