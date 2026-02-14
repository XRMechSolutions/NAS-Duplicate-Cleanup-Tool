"""Fill gaps in recovered JPEG images using available thumbnail data."""

import io

import numpy as np
from PIL import Image, ImageDraw

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class JPEGGapFiller:
    """Fill missing/corrupt areas in recovered JPEGs using thumbnail upscaling."""

    def __init__(self):
        """Initialize gap filler."""
        pass

    def detect_gaps(self, img: Image.Image, _threshold: float = 0.1) -> float:
        """Detect percentage of image that is gray/missing.

        Args:
            img: PIL Image
            threshold: Minimum percentage to consider as having gaps

        Returns:
            Percentage of image that is missing (0-100)
        """
        img_array = np.array(img)

        # Check for gray pixels (128,128,128) - common PIL placeholder
        if len(img_array.shape) == 3:
            gray_mask = np.all(img_array == 128, axis=2)
        else:
            gray_mask = img_array == 128

        gray_count = np.sum(gray_mask)
        total_pixels = img.size[0] * img.size[1]
        gap_percentage = (gray_count / total_pixels) * 100

        logger.info(f"Gap detection: {gap_percentage:.1f}% gray pixels")
        return gap_percentage

    def find_all_valid_thumbnails(self, corrupt_file_path: str) -> list[tuple[int, int, Image.Image]]:
        """Find all valid thumbnail images in a corrupt file.

        Args:
            corrupt_file_path: Path to corrupt JPEG file

        Returns:
            List of (width, height, image) tuples, sorted by size descending
        """
        thumbnails = []

        try:
            with open(corrupt_file_path, 'rb') as f:
                data = f.read()

            # Find all SOI markers
            soi_positions = []
            for i in range(len(data) - 1):
                if data[i] == 0xFF and data[i+1] == 0xD8:
                    soi_positions.append(i)

            logger.info(f"Found {len(soi_positions)} potential image segments")

            # Test each segment
            for soi_pos in soi_positions:
                segment = data[soi_pos:]

                try:
                    img = Image.open(io.BytesIO(segment))
                    img.load()  # Force decode

                    # Skip if too small (probably corrupt data, not real thumbnail)
                    if img.size[0] < 50 or img.size[1] < 50:
                        continue

                    # Check if it's mostly gray (missing data)
                    img_array = np.array(img)
                    if len(img_array.shape) == 3:
                        gray_mask = np.all(img_array == 128, axis=2)
                    else:
                        gray_mask = img_array == 128

                    gray_percentage = (np.sum(gray_mask) / (img.size[0] * img.size[1])) * 100

                    # Only keep if <50% gray (has real image data)
                    if gray_percentage < 50:
                        thumbnails.append((img.size[0], img.size[1], img.copy()))
                        logger.info(f"  Valid thumbnail: {img.size[0]}x{img.size[1]} ({gray_percentage:.1f}% gaps)")

                except Exception:
                    pass

            # Sort by total pixels (largest first)
            thumbnails.sort(key=lambda x: x[0] * x[1], reverse=True)

            return thumbnails

        except Exception as e:
            logger.error(f"Failed to find thumbnails: {e}")
            return []

    def fill_gaps_with_thumbnail(self,
                                 target_size: tuple[int, int],
                                 thumbnail: Image.Image,
                                 _exif_data: bytes | None = None) -> Image.Image:
        """Fill a full-size image by upscaling thumbnail.

        Args:
            target_size: Target image dimensions (width, height)
            thumbnail: Valid thumbnail image to upscale
            exif_data: Optional EXIF data to preserve

        Returns:
            Filled image
        """
        logger.info(f"Upscaling {thumbnail.size[0]}x{thumbnail.size[1]} to {target_size[0]}x{target_size[1]}")

        # Use high-quality Lanczos resampling
        upscaled = thumbnail.resize(target_size, Image.Resampling.LANCZOS)

        # Add watermark indicating this is upscaled
        draw = ImageDraw.Draw(upscaled)

        # Calculate watermark position (bottom right)
        watermark_text = f"Upscaled from {thumbnail.size[0]}x{thumbnail.size[1]}"
        text_bbox = draw.textbbox((0, 0), watermark_text)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        x = target_size[0] - text_width - 20
        y = target_size[1] - text_height - 20

        # Draw semi-transparent background for text
        draw.rectangle([x-5, y-5, x+text_width+5, y+text_height+5], fill=(0, 0, 0, 128))
        draw.text((x, y), watermark_text, fill=(255, 255, 255))

        return upscaled

    def recover_with_gap_filling(self,
                                 corrupt_file_path: str,
                                 output_path: str,
                                 target_size: tuple[int, int] | None = None,
                                 exif_data: bytes | None = None) -> str | None:
        """Recover JPEG with automatic gap filling using thumbnails.

        Args:
            corrupt_file_path: Path to corrupt JPEG
            output_path: Path to save recovered JPEG
            target_size: Target dimensions (from EXIF), or None to detect
            exif_data: Optional EXIF data to preserve

        Returns:
            Path to recovered file if successful, None otherwise
        """
        logger.info(f"Recovering with gap filling: {corrupt_file_path}")

        try:
            # Find all valid thumbnails
            thumbnails = self.find_all_valid_thumbnails(corrupt_file_path)

            if not thumbnails:
                logger.error("No valid thumbnails found for gap filling")
                return None

            # Use largest thumbnail
            width, height, best_thumbnail = thumbnails[0]
            logger.info(f"Using best thumbnail: {width}x{height} pixels")

            # Determine target size
            if target_size is None:
                # Use 4x upscale of thumbnail
                target_size = (width * 4, height * 4)
                logger.info(f"No target size specified, using 4x upscale: {target_size[0]}x{target_size[1]}")

            # Fill gaps by upscaling
            recovered = self.fill_gaps_with_thumbnail(target_size, best_thumbnail, exif_data)

            # Save with EXIF if available
            if exif_data:
                recovered.save(output_path, 'JPEG', quality=95, exif=exif_data)
            else:
                recovered.save(output_path, 'JPEG', quality=95)

            logger.info(f"Saved gap-filled image to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Gap filling failed: {e}")
            return None


def fill_jpeg_gaps(corrupt_file_path: str,
                   output_path: str,
                   target_size: tuple[int, int] | None = None,
                   exif_data: bytes | None = None) -> str | None:
    """Convenience function for gap filling.

    Args:
        corrupt_file_path: Path to corrupt JPEG
        output_path: Path to save recovered JPEG
        target_size: Target dimensions (from EXIF), or None to auto-detect
        exif_data: Optional EXIF data to preserve

    Returns:
        Path to recovered file if successful, None otherwise
    """
    filler = JPEGGapFiller()
    return filler.recover_with_gap_filling(corrupt_file_path, output_path, target_size, exif_data)
