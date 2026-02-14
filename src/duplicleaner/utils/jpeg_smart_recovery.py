"""Smart JPEG recovery using multi-SOI extraction.

This module repairs corrupt JPEG files by finding embedded JPEG streams
at different offsets within the file and extracting the best valid one.
"""

import contextlib
from pathlib import Path

from PIL import Image

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class JPEGSmartRecovery:
    """Smart JPEG recovery using multi-SOI extraction."""

    def __init__(self):
        """Initialize smart recovery."""
        self.temp_counter = 0

    def find_soi_markers(self, data: bytes) -> list[int]:
        """Find all Start Of Image (SOI) markers in data.

        Args:
            data: Raw file bytes

        Returns:
            List of byte offsets where SOI markers (FF D8) are found
        """
        soi_positions = []
        for i in range(len(data) - 1):
            if data[i] == 0xFF and data[i + 1] == 0xD8:
                soi_positions.append(i)
        return soi_positions

    def test_jpeg_segment(self, data: bytes, temp_dir: str | None = None) -> tuple[int, int, str] | None:
        """Test if a data segment is a valid, fully decodable JPEG.

        Args:
            data: JPEG data to test
            temp_dir: Directory for temporary test file

        Returns:
            Tuple of (width, height, mode) if valid, None otherwise
        """
        if temp_dir is None:
            temp_dir = Path.home() / "Documents" / "jpeg_recovery_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

        self.temp_counter += 1
        temp_file = temp_dir / f"test_{self.temp_counter}.jpg"

        try:
            # Write test file
            with open(temp_file, 'wb') as f:
                f.write(data)

            # Try to open and fully decode
            with Image.open(temp_file) as img:
                img.load()  # Force full decode
                return (img.size[0], img.size[1], img.mode)

        except Exception:
            return None
        finally:
            # Clean up temp file
            if temp_file.exists():
                with contextlib.suppress(BaseException):
                    temp_file.unlink()

    def recover_jpeg(self, input_path: str, output_path: str | None = None) -> str | None:
        """Recover a corrupt JPEG file using multi-SOI extraction.

        Args:
            input_path: Path to corrupt JPEG
            output_path: Optional path to save recovered JPEG

        Returns:
            Path to recovered file if successful, None otherwise
        """
        logger.info(f"Attempting smart JPEG recovery: {input_path}")

        try:
            # Read file
            with open(input_path, 'rb') as f:
                data = f.read()

            file_size = len(data)
            logger.info(f"File size: {file_size:,} bytes")

            # Find all SOI markers
            soi_positions = self.find_soi_markers(data)
            logger.info(f"Found {len(soi_positions)} SOI markers at: {soi_positions[:10]}")

            if not soi_positions:
                logger.error("No SOI markers found - not a JPEG file")
                return None

            # Test each SOI position (extract from SOI to EOF)
            valid_segments = []
            temp_dir = Path.home() / "Documents" / "jpeg_recovery_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            for soi_pos in soi_positions:
                segment = data[soi_pos:]
                result = self.test_jpeg_segment(segment, temp_dir)

                if result:
                    width, height, mode = result
                    logger.info(f"Valid segment at offset {soi_pos}: {width}x{height} ({len(segment):,} bytes)")
                    valid_segments.append({
                        'offset': soi_pos,
                        'width': width,
                        'height': height,
                        'mode': mode,
                        'bytes': len(segment),
                        'data': segment
                    })

            if not valid_segments:
                logger.error("No valid JPEG segments found")
                return None

            # Select best segment (largest dimensions)
            best = max(valid_segments, key=lambda x: x['width'] * x['height'])
            logger.info(f"Best segment: offset {best['offset']}, {best['width']}x{best['height']} pixels")

            # Determine output path
            if output_path is None:
                input_name = Path(input_path).stem
                output_dir = Path.home() / "Documents" / "Recovered_JPEGs"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = str(output_dir / f"{input_name}_recovered.jpg")

            # Save recovered JPEG
            with open(output_path, 'wb') as f:
                f.write(best['data'])

            logger.info(f"Recovered JPEG saved: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Smart recovery failed: {e}")
            return None


def recover_jpeg_smart(input_path: str, output_path: str | None = None) -> str | None:
    """Convenience function for smart JPEG recovery.

    Args:
        input_path: Path to corrupt JPEG
        output_path: Optional path to save recovered JPEG

    Returns:
        Path to recovered file if successful, None otherwise
    """
    recovery = JPEGSmartRecovery()
    return recovery.recover_jpeg(input_path, output_path)


def recover_jpeg_for_analysis(input_path: str) -> str | None:
    """Recover a corrupt JPEG for AI analysis.

    Creates a temporary recovered version suitable for face detection.

    Args:
        input_path: Path to corrupt JPEG

    Returns:
        Path to recovered temporary file, or None if recovery failed
    """
    temp_dir = Path.home() / "Documents" / "jpeg_recovery_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(input_path).name
    output_path = str(temp_dir / f"recovered_{filename}")

    return recover_jpeg_smart(input_path, output_path)
