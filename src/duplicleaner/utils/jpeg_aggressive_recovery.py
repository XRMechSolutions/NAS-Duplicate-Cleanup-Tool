"""Aggressive JPEG recovery attempting to extract partial full-size images.

This module attempts to recover the maximum possible image data from corrupt JPEGs,
including partial/truncated full-size images, and preserves EXIF metadata.
"""

import io
import struct

from PIL import Image, ImageFile

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Allow loading truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True


class JPEGAggressiveRecovery:
    """Aggressive recovery for severely corrupt/truncated JPEG files."""

    def __init__(self):
        """Initialize aggressive recovery."""
        pass

    def extract_exif_data(self, file_path: str) -> bytes | None:
        """Extract EXIF data from corrupt JPEG.

        Args:
            file_path: Path to JPEG file

        Returns:
            EXIF data bytes if found, None otherwise
        """
        try:
            with open(file_path, 'rb') as f:
                data = f.read(100000)  # Read first 100KB for EXIF

            # Find APP1 (EXIF) marker
            idx = 0
            while idx < len(data) - 4:
                if data[idx] == 0xFF and data[idx+1] == 0xE1:
                    # Found APP1 marker
                    segment_length = struct.unpack('>H', data[idx+2:idx+4])[0]
                    exif_data = data[idx:idx+2+segment_length]

                    # Verify it's EXIF
                    if b'Exif\x00\x00' in exif_data[:10]:
                        logger.info(f"Extracted {len(exif_data)} bytes of EXIF data")
                        return exif_data
                idx += 1

            return None

        except Exception as e:
            logger.error(f"Failed to extract EXIF: {e}")
            return None

    def get_exif_dimensions(self, file_path: str) -> tuple[int, int] | None:
        """Get original image dimensions from EXIF.

        Args:
            file_path: Path to JPEG file

        Returns:
            Tuple of (width, height) if found, None otherwise
        """
        try:
            with open(file_path, 'rb') as f:
                data = f.read(2000)

            # Look for ExifImageWidth (0xA002) and ExifImageHeight (0xA003)
            width_idx = data.find(b'\xa0\x02')
            height_idx = data.find(b'\xa0\x03')

            if width_idx != -1 and height_idx != -1:
                # Read dimensions (big-endian 4-byte integers at offset +8)
                width = struct.unpack('>I', data[width_idx+8:width_idx+12])[0]
                height = struct.unpack('>I', data[height_idx+8:height_idx+12])[0]

                if 100 < width < 10000 and 100 < height < 10000:  # Sanity check
                    logger.info(f"EXIF dimensions: {width}x{height}")
                    return (width, height)

            return None

        except Exception as e:
            logger.error(f"Failed to get EXIF dimensions: {e}")
            return None

    def find_full_size_image_offset(self, data: bytes, expected_width: int = 2048) -> int | None:
        """Find the offset of the full-size image data.

        Args:
            data: Raw file bytes
            expected_width: Expected image width

        Returns:
            Offset of full-size image start, or None
        """
        # Look for SOF (Start Of Frame) markers that indicate the full-size image
        # SOF0 = 0xFFC0, contains image dimensions

        idx = 0
        while idx < len(data) - 10:
            if data[idx] == 0xFF and data[idx+1] == 0xC0:
                # Found SOF0 marker
                # Format: FF C0 [length:2] [precision:1] [height:2] [width:2]
                struct.unpack('>H', data[idx+2:idx+4])[0]
                height = struct.unpack('>H', data[idx+5:idx+7])[0]
                width = struct.unpack('>H', data[idx+7:idx+9])[0]

                logger.info(f"Found SOF0 at offset {idx}: {width}x{height}")

                # Check if this matches expected dimensions
                if width >= expected_width * 0.8:  # Within 20% of expected
                    # Look backwards for the SOI marker of this image
                    search_start = max(0, idx - 10000)
                    for j in range(idx, search_start, -1):
                        if data[j] == 0xFF and data[j+1] == 0xD8:
                            logger.info(f"Found matching SOI at offset {j}")
                            return j
            idx += 1

        return None

    def recover_partial_image(self, input_path: str, output_path: str) -> str | None:
        """Recover partial full-size image with EXIF preservation.

        Args:
            input_path: Path to corrupt JPEG
            output_path: Path to save recovered JPEG

        Returns:
            Path to recovered file if successful, None otherwise
        """
        logger.info(f"Attempting aggressive recovery: {input_path}")

        try:
            # Read file
            with open(input_path, 'rb') as f:
                data = f.read()

            logger.info(f"File size: {len(data):,} bytes")

            # Get expected dimensions from EXIF
            expected_dims = self.get_exif_dimensions(input_path)
            if not expected_dims:
                logger.warning("Could not determine expected dimensions from EXIF")
                expected_width = 2048  # Default FinePix F450 width
            else:
                expected_width = expected_dims[0]

            # Extract EXIF data
            exif_data = self.extract_exif_data(input_path)

            # Find all SOI markers
            soi_positions = []
            for i in range(len(data) - 1):
                if data[i] == 0xFF and data[i+1] == 0xD8:
                    soi_positions.append(i)

            logger.info(f"Found {len(soi_positions)} SOI markers")

            # Try to find the full-size image
            full_size_offset = self.find_full_size_image_offset(data, expected_width)

            if full_size_offset is None:
                logger.warning("Could not find full-size image section")
                # Try each SOI position
                candidates = []
                for soi_pos in soi_positions:
                    segment = data[soi_pos:]
                    try:
                        img = Image.open(io.BytesIO(segment))
                        img.load()  # Force decode
                        candidates.append((soi_pos, img.size, segment))
                        logger.info(f"  Offset {soi_pos}: {img.size[0]}x{img.size[1]} - VALID")
                    except Exception as e:
                        logger.debug(f"  Offset {soi_pos}: FAILED - {str(e)[:50]}")

                if not candidates:
                    logger.error("No valid image segments found")
                    return None

                # Use largest valid segment
                full_size_offset, size, segment = max(candidates, key=lambda x: x[1][0] * x[1][1])
                logger.info(f"Using largest segment at offset {full_size_offset}: {size[0]}x{size[1]}")

            # Extract from full-size offset
            full_size_data = data[full_size_offset:]

            # Try to decode with truncation allowed
            try:
                img = Image.open(io.BytesIO(full_size_data))
                img.load()  # Force decode (will decode partial image)

                logger.info(f"Recovered partial image: {img.size[0]}x{img.size[1]} pixels, mode={img.mode}")

                # If we have EXIF data and the image doesn't, add it
                if exif_data:
                    logger.info("Preserving EXIF metadata")
                    # Save with EXIF
                    img.save(output_path, 'JPEG', quality=95, exif=exif_data)
                else:
                    img.save(output_path, 'JPEG', quality=95)

                logger.info(f"Saved recovered image to: {output_path}")
                return output_path

            except Exception as e:
                logger.error(f"Failed to decode image: {e}")
                return None

        except Exception as e:
            logger.error(f"Aggressive recovery failed: {e}")
            return None


def recover_jpeg_aggressive(input_path: str, output_path: str) -> str | None:
    """Convenience function for aggressive JPEG recovery.

    Args:
        input_path: Path to corrupt JPEG
        output_path: Path to save recovered JPEG

    Returns:
        Path to recovered file if successful, None otherwise
    """
    recovery = JPEGAggressiveRecovery()
    return recovery.recover_partial_image(input_path, output_path)
