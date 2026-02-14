"""Deep JPEG recovery - extract maximum data from corrupt files using error-tolerant decoding."""

import io
import struct

import numpy as np
from PIL import Image, ImageFile

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Enable aggressive truncation handling
ImageFile.LOAD_TRUNCATED_IMAGES = True
ImageFile.MAXBLOCK = 2**20  # 1MB blocks


class JPEGDeepRecovery:
    """Deep recovery using error-tolerant JPEG decoding."""

    def __init__(self):
        """Initialize deep recovery."""
        pass

    def try_decode_with_padding(self, data: bytes, _target_size: tuple[int, int]) -> Image.Image | None:
        """Try to decode JPEG by padding with valid EOI markers at different positions.

        Args:
            data: Corrupt JPEG data
            target_size: Expected image dimensions

        Returns:
            Best recovered image, or None
        """
        logger.info("Attempting decode with padding strategy")

        best_img = None
        best_decoded_size = 0

        # Try adding EOI at various positions in the last 20% of file
        file_size = len(data)
        test_positions = []

        # Test every 1KB in the last portion
        start_pos = max(10000, file_size - 100000)
        for pos in range(start_pos, file_size, 1024):
            test_positions.append(pos)

        # Always test the very end
        test_positions.append(file_size)

        for pos in test_positions:
            # Truncate at this position and add EOI
            test_data = data[:pos]

            # If doesn't end with EOI, add it
            if not test_data.endswith(b'\xFF\xD9'):
                test_data += b'\xFF\xD9'

            try:
                img = Image.open(io.BytesIO(test_data))
                img.load()

                # Check how much we decoded
                img_array = np.array(img)

                # Count non-gray pixels
                if len(img_array.shape) == 3:
                    non_gray = np.sum(~np.all(img_array == 128, axis=2))
                else:
                    non_gray = np.sum(img_array != 128)

                if non_gray > best_decoded_size:
                    best_decoded_size = non_gray
                    best_img = img.copy()
                    logger.info(f"  Position {pos}: decoded {non_gray:,} pixels")

            except Exception:
                continue

        if best_img:
            logger.info(f"Best decode recovered {best_decoded_size:,} pixels")
            return best_img

        return None

    def extract_scan_data(self, data: bytes) -> bytes | None:
        """Extract the actual scan data (compressed image) from JPEG.

        Args:
            data: JPEG file bytes

        Returns:
            Scan data bytes starting from SOS marker
        """
        # Find SOS (Start Of Scan) marker - this is where image data begins
        sos_idx = data.find(b'\xFF\xDA')

        if sos_idx == -1:
            logger.error("No SOS marker found")
            return None

        # SOS marker format: FF DA [length:2] [data...]
        sos_length = struct.unpack('>H', data[sos_idx+2:sos_idx+4])[0]

        # Scan data starts after SOS header
        scan_start = sos_idx + 2 + sos_length

        logger.info(f"Found scan data at offset {scan_start}")
        return data[scan_start:]

    def find_restart_markers(self, scan_data: bytes) -> list:
        """Find all restart markers in scan data.

        Restart markers (RST0-RST7) segment the image, allowing partial recovery.

        Args:
            scan_data: Compressed image data

        Returns:
            List of restart marker positions
        """
        markers = []

        for i in range(len(scan_data) - 1):
            if scan_data[i] == 0xFF:
                marker = scan_data[i+1]
                # RST markers are 0xD0 to 0xD7
                if 0xD0 <= marker <= 0xD7:
                    markers.append((i, marker))

        logger.info(f"Found {len(markers)} restart markers")
        return markers

    def recover_using_restart_markers(self, file_path: str, output_path: str) -> str | None:
        """Attempt recovery using JPEG restart markers for error isolation.

        Args:
            file_path: Path to corrupt JPEG
            output_path: Path to save recovered image

        Returns:
            Path to recovered file if successful
        """
        logger.info(f"Attempting restart marker recovery: {file_path}")

        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            # Find all SOI markers
            soi_positions = []
            for i in range(len(data) - 1):
                if data[i] == 0xFF and data[i+1] == 0xD8:
                    soi_positions.append(i)

            logger.info(f"Found {len(soi_positions)} SOI markers")

            best_result = None
            best_pixel_count = 0

            # Try each SOI position
            for soi_idx, soi_pos in enumerate(soi_positions):
                segment = data[soi_pos:]

                # Try standard decode first
                try:
                    img = Image.open(io.BytesIO(segment))
                    img.load()

                    img_array = np.array(img)
                    if len(img_array.shape) == 3:
                        non_gray = np.sum(~np.all(img_array == 128, axis=2))
                    else:
                        non_gray = np.sum(img_array != 128)

                    if non_gray > best_pixel_count:
                        best_pixel_count = non_gray
                        best_result = img.copy()
                        logger.info(f"  SOI {soi_idx} at {soi_pos}: {non_gray:,} pixels decoded")

                except Exception:
                    pass

                # Try padding strategy for this segment
                padded_result = self.try_decode_with_padding(segment, (640, 480))
                if padded_result:
                    img_array = np.array(padded_result)
                    if len(img_array.shape) == 3:
                        non_gray = np.sum(~np.all(img_array == 128, axis=2))
                    else:
                        non_gray = np.sum(img_array != 128)

                    if non_gray > best_pixel_count:
                        best_pixel_count = non_gray
                        best_result = padded_result
                        logger.info(f"  SOI {soi_idx} with padding: {non_gray:,} pixels decoded")

            if best_result:
                best_result.save(output_path, 'JPEG', quality=95)
                logger.info(f"Deep recovery saved: {output_path}")
                return output_path

            return None

        except Exception as e:
            logger.error(f"Deep recovery failed: {e}")
            return None


def deep_recover_jpeg(input_path: str, output_path: str) -> str | None:
    """Convenience function for deep JPEG recovery.

    Args:
        input_path: Path to corrupt JPEG
        output_path: Path to save recovered image

    Returns:
        Path to recovered file if successful
    """
    recovery = JPEGDeepRecovery()
    return recovery.recover_using_restart_markers(input_path, output_path)
