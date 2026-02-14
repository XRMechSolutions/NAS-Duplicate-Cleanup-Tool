"""Hybrid JPEG recovery - combine actual data recovery with intelligent gap filling."""

from pathlib import Path

import numpy as np
from PIL import Image

from duplicleaner.utils.jpeg_aggressive_recovery import JPEGAggressiveRecovery
from duplicleaner.utils.jpeg_deep_recovery import JPEGDeepRecovery
from duplicleaner.utils.jpeg_gap_filler import JPEGGapFiller
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class JPEGHybridRecovery:
    """Hybrid recovery combining actual data extraction with intelligent gap filling."""

    def __init__(self):
        """Initialize hybrid recovery."""
        self.deep_recovery = JPEGDeepRecovery()
        self.gap_filler = JPEGGapFiller()
        self.aggressive_recovery = JPEGAggressiveRecovery()

    def merge_images(self,
                    actual_data_img: Image.Image,
                    upscaled_img: Image.Image,
                    target_size: tuple[int, int]) -> Image.Image:
        """Merge actual recovered data with upscaled thumbnail.

        Args:
            actual_data_img: Image with actual recovered data (may have gray gaps)
            upscaled_img: Upscaled thumbnail to fill gaps
            target_size: Final output size

        Returns:
            Merged image
        """
        logger.info(f"Merging actual data {actual_data_img.size} with upscaled {upscaled_img.size} -> {target_size}")

        # Resize both to target size
        actual_resized = actual_data_img.resize(target_size, Image.Resampling.LANCZOS)
        upscaled_resized = upscaled_img.resize(target_size, Image.Resampling.LANCZOS)

        # Convert to arrays
        actual_array = np.array(actual_resized)
        upscaled_array = np.array(upscaled_resized)

        # Create mask for gray (missing) pixels in actual data
        if len(actual_array.shape) == 3:
            gray_mask = np.all(actual_array == 128, axis=2)
        else:
            gray_mask = actual_array == 128

        # Create merged image: use actual data where available, upscaled where missing
        merged_array = actual_array.copy()

        if len(merged_array.shape) == 3:
            # RGB image
            for c in range(3):
                merged_array[:, :, c][gray_mask] = upscaled_array[:, :, c][gray_mask]
        else:
            # Grayscale
            merged_array[gray_mask] = upscaled_array[gray_mask]

        # Calculate coverage
        total_pixels = target_size[0] * target_size[1]
        actual_pixels = total_pixels - np.sum(gray_mask)
        filled_pixels = np.sum(gray_mask)

        logger.info(f"  Actual data: {actual_pixels:,} pixels ({100*actual_pixels/total_pixels:.1f}%)")
        logger.info(f"  Filled gaps: {filled_pixels:,} pixels ({100*filled_pixels/total_pixels:.1f}%)")

        return Image.fromarray(merged_array)

    def recover_hybrid(self,
                      corrupt_file_path: str,
                      output_path: str,
                      exif_data: bytes | None = None) -> str | None:
        """Perform hybrid recovery combining all techniques.

        Args:
            corrupt_file_path: Path to corrupt JPEG
            output_path: Path to save recovered image
            exif_data: Optional EXIF data to preserve

        Returns:
            Path to recovered file if successful
        """
        logger.info(f"Hybrid recovery: {corrupt_file_path}")

        try:
            # Get target dimensions from EXIF
            target_dims = self.aggressive_recovery.get_exif_dimensions(corrupt_file_path)
            if not target_dims:
                target_dims = (640, 480)  # Default

            logger.info(f"Target dimensions: {target_dims[0]}x{target_dims[1]}")

            # Step 1: Deep recovery to get maximum actual data
            temp_deep = Path(output_path).parent / f"temp_deep_{Path(output_path).name}"
            deep_result = self.deep_recovery.recover_using_restart_markers(
                corrupt_file_path,
                str(temp_deep)
            )

            # Step 2: Find best thumbnail for gap filling
            thumbnails = self.gap_filler.find_all_valid_thumbnails(corrupt_file_path)

            if not thumbnails and not deep_result:
                logger.error("No data could be recovered")
                return None

            # Step 3: Create hybrid image
            if deep_result and thumbnails:
                # We have both - merge them!
                logger.info("Creating hybrid from actual data + thumbnail")

                with Image.open(deep_result) as actual_img:
                    # Get best thumbnail
                    _, _, best_thumbnail = thumbnails[0]

                    # Upscale thumbnail to target size
                    upscaled_thumbnail = best_thumbnail.resize(target_dims, Image.Resampling.LANCZOS)

                    # Merge
                    merged = self.merge_images(actual_img, upscaled_thumbnail, target_dims)

                    # Save with EXIF
                    if exif_data:
                        merged.save(output_path, 'JPEG', quality=95, exif=exif_data)
                    else:
                        merged.save(output_path, 'JPEG', quality=95)

                # Clean up temp file
                if temp_deep.exists():
                    temp_deep.unlink()

                logger.info(f"Saved hybrid recovery: {output_path}")
                return output_path

            elif deep_result:
                # Only have deep recovery - use it directly
                logger.info("Using deep recovery only")
                if temp_deep.exists():
                    temp_deep.rename(output_path)
                return output_path

            elif thumbnails:
                # Only have thumbnail - upscale it
                logger.info("Using thumbnail upscaling only")
                _, _, best_thumbnail = thumbnails[0]
                upscaled = best_thumbnail.resize(target_dims, Image.Resampling.LANCZOS)

                if exif_data:
                    upscaled.save(output_path, 'JPEG', quality=95, exif=exif_data)
                else:
                    upscaled.save(output_path, 'JPEG', quality=95)

                return output_path

        except Exception as e:
            logger.error(f"Hybrid recovery failed: {e}")
            import traceback
            traceback.print_exc()
            return None


def hybrid_recover_jpeg(corrupt_file_path: str,
                       output_path: str,
                       exif_data: bytes | None = None) -> str | None:
    """Convenience function for hybrid JPEG recovery.

    Args:
        corrupt_file_path: Path to corrupt JPEG
        output_path: Path to save recovered image
        exif_data: Optional EXIF data to preserve

    Returns:
        Path to recovered file if successful
    """
    recovery = JPEGHybridRecovery()
    return recovery.recover_hybrid(corrupt_file_path, output_path, exif_data)
