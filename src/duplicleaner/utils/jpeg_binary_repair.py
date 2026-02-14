"""Binary-level JPEG repair utilities.

This module repairs corrupt JPEG files by working at the raw byte level:
- Locates and validates JPEG markers
- Strips extraneous bytes
- Reconstructs JPEG structure
- Attempts to salvage partial images
"""

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# JPEG markers
JPEG_SOI = b'\xff\xd8'  # Start Of Image
JPEG_EOI = b'\xff\xd9'  # End Of Image
JPEG_SOS = b'\xff\xda'  # Start Of Scan (image data begins)
JPEG_APP0 = b'\xff\xe0'  # JFIF marker
JPEG_APP1 = b'\xff\xe1'  # EXIF marker


class JPEGBinaryRepairer:
    """Repairs corrupt JPEG files at the binary level."""

    def __init__(self):
        """Initialize JPEG binary repairer."""
        pass

    def find_jpeg_markers(self, data: bytes) -> list[tuple[int, bytes]]:
        """Find all JPEG markers in binary data.

        Args:
            data: Raw file bytes

        Returns:
            List of (offset, marker) tuples
        """
        markers = []
        i = 0
        while i < len(data) - 1:
            if data[i] == 0xFF and data[i+1] != 0x00 and data[i+1] != 0xFF:
                marker = bytes([data[i], data[i+1]])
                markers.append((i, marker))
                i += 2
            else:
                i += 1
        return markers

    def extract_clean_jpeg(self, file_path: str) -> bytes | None:
        """Extract clean JPEG data from a corrupt file.

        Args:
            file_path: Path to corrupt JPEG

        Returns:
            Clean JPEG bytes if successful, None otherwise
        """
        logger.info(f"Attempting binary repair of: {file_path}")

        try:
            # Read the entire file
            with open(file_path, 'rb') as f:
                data = f.read()

            logger.info(f"File size: {len(data)} bytes")

            # Find SOI (Start Of Image) marker
            soi_offset = data.find(JPEG_SOI)
            if soi_offset == -1:
                logger.error("No JPEG SOI marker found")
                return None

            logger.info(f"Found SOI at offset: {soi_offset}")

            # If SOI is not at start, there's junk before it
            if soi_offset > 0:
                logger.info(f"Stripping {soi_offset} bytes of junk before SOI")
                data = data[soi_offset:]

            # Find all markers
            markers = self.find_jpeg_markers(data)
            logger.info(f"Found {len(markers)} JPEG markers")

            # Find EOI (End Of Image) marker
            eoi_offset = data.rfind(JPEG_EOI)
            if eoi_offset == -1:
                logger.warning("No EOI marker found - image may be truncated")
                # Try to find last valid marker and add EOI
                if markers:
                    last_marker_offset = markers[-1][0]
                    # Add some padding and EOI
                    data = data[:last_marker_offset + 1000] + JPEG_EOI
                    logger.info("Added EOI marker at estimated end")
            else:
                logger.info(f"Found EOI at offset: {eoi_offset}")
                # Trim everything after EOI
                if eoi_offset + 2 < len(data):
                    extra_bytes = len(data) - (eoi_offset + 2)
                    logger.info(f"Stripping {extra_bytes} bytes after EOI")
                    data = data[:eoi_offset + 2]

            # Validate structure
            if not data.startswith(JPEG_SOI):
                logger.error("Repaired data doesn't start with SOI")
                return None

            if not data.endswith(JPEG_EOI):
                logger.warning("Repaired data doesn't end with EOI - adding it")
                data += JPEG_EOI

            logger.info(f"Repaired JPEG size: {len(data)} bytes")
            return data

        except Exception as e:
            logger.error(f"Binary repair failed: {e}")
            return None

    def repair_jpeg(self, input_path: str, output_path: str) -> bool:
        """Repair a corrupt JPEG file.

        Args:
            input_path: Path to corrupt JPEG
            output_path: Path to save repaired JPEG

        Returns:
            True if successful, False otherwise
        """
        # Extract clean data
        clean_data = self.extract_clean_jpeg(input_path)

        if clean_data is None:
            return False

        # Write repaired file
        try:
            with open(output_path, 'wb') as f:
                f.write(clean_data)

            logger.info(f"Saved repaired JPEG to: {output_path}")

            # Verify it can be opened
            try:
                from PIL import Image
                with Image.open(output_path) as img:
                    img.load()
                logger.info("✓ Repaired JPEG verified successfully")
                return True
            except Exception as e:
                logger.warning(f"Repaired JPEG may still have issues: {e}")
                # Don't fail - file might still be partially viewable
                return True

        except Exception as e:
            logger.error(f"Failed to write repaired file: {e}")
            return False

    def attempt_aggressive_repair(self, file_path: str) -> bytes | None:
        """Attempt very aggressive repair by scanning for image data.

        This method tries to recover at least partial image data from
        severely corrupt files.

        Args:
            file_path: Path to corrupt JPEG

        Returns:
            Best attempt at JPEG bytes, or None
        """
        logger.info(f"Attempting aggressive repair: {file_path}")

        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            # Look for any JPEG-like patterns
            soi_positions = []
            pos = 0
            while True:
                pos = data.find(JPEG_SOI, pos)
                if pos == -1:
                    break
                soi_positions.append(pos)
                pos += 2

            if not soi_positions:
                logger.error("No JPEG patterns found at all")
                return None

            logger.info(f"Found {len(soi_positions)} potential JPEG starts")

            # Try each potential start
            best_data = None
            best_size = 0

            for soi_pos in soi_positions:
                # Extract from this position to end
                segment = data[soi_pos:]

                # Look for EOI
                eoi_pos = segment.find(JPEG_EOI)
                if eoi_pos != -1:
                    candidate = segment[:eoi_pos + 2]
                else:
                    # No EOI, take what we have and add one
                    candidate = segment[:min(len(segment), 1000000)] + JPEG_EOI

                # Keep the largest valid-looking segment
                if len(candidate) > best_size and candidate.startswith(JPEG_SOI):
                    best_data = candidate
                    best_size = len(candidate)

            if best_data:
                logger.info(f"Extracted {best_size} bytes from aggressive scan")
                return best_data

            return None

        except Exception as e:
            logger.error(f"Aggressive repair failed: {e}")
            return None


def repair_jpeg_file(input_path: str, output_path: str, aggressive: bool = False) -> bool:
    """Convenience function to repair a JPEG file.

    Args:
        input_path: Path to corrupt JPEG
        output_path: Path to save repaired JPEG
        aggressive: If True, use aggressive repair

    Returns:
        True if successful
    """
    repairer = JPEGBinaryRepairer()

    if aggressive:
        clean_data = repairer.attempt_aggressive_repair(input_path)
        if clean_data:
            try:
                with open(output_path, 'wb') as f:
                    f.write(clean_data)
                return True
            except Exception as e:
                logger.error(f"Failed to write file: {e}")
                return False
    else:
        return repairer.repair_jpeg(input_path, output_path)

    return False
