"""JPEG Recovery Utilities

Automatically detects and repairs corrupt JPEG files by:
- Reading with PIL in tolerant mode
- Stripping corrupt metadata
- Re-encoding to clean JPEG format
- Preserving valid EXIF data
"""

import os
import shutil
from pathlib import Path

from PIL import Image, ImageFile

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Allow PIL to load truncated/corrupt images
ImageFile.LOAD_TRUNCATED_IMAGES = True


class JPEGRecoveryResult:
    """Result of JPEG recovery attempt."""

    def __init__(
        self,
        success: bool,
        original_path: str,
        recovered_path: str | None = None,
        error: str | None = None,
        corruption_type: str | None = None,
    ):
        self.success = success
        self.original_path = original_path
        self.recovered_path = recovered_path
        self.error = error
        self.corruption_type = corruption_type


class JPEGRecovery:
    """Handles automatic recovery of corrupt JPEG files."""

    def __init__(
        self,
        recovery_dir: str | None = None,
        preserve_originals: bool = True,
        quality: int = 95,
    ):
        """Initialize JPEG recovery.

        Args:
            recovery_dir: Directory to save recovered files (None = same dir as original)
            preserve_originals: If True, keep original corrupt files
            quality: JPEG quality for recovered files (1-100)
        """
        self.recovery_dir = Path(recovery_dir) if recovery_dir else None
        self.preserve_originals = preserve_originals
        self.quality = quality

        if self.recovery_dir:
            self.recovery_dir.mkdir(parents=True, exist_ok=True)

    def is_corrupt_jpeg(self, file_path: str) -> tuple[bool, str | None]:
        """Check if a JPEG file is corrupt.

        Args:
            file_path: Path to JPEG file

        Returns:
            Tuple of (is_corrupt, corruption_description)
        """
        if not os.path.exists(file_path):
            return False, None

        # Try to open with PIL
        try:
            with Image.open(file_path) as img:
                # Force load to detect corruption
                img.verify()
            return False, None
        except (OSError, Image.DecompressionBombError) as e:
            error_msg = str(e).lower()

            # Classify corruption type
            if "truncated" in error_msg or "premature" in error_msg:
                return True, "truncated"
            elif "extraneous" in error_msg or "corrupt" in error_msg:
                return True, "extraneous_data"
            elif "marker" in error_msg:
                return True, "invalid_markers"
            else:
                return True, "unknown"
        except Exception as e:
            logger.debug(f"Error checking JPEG {file_path}: {e}")
            return False, None

    def recover_jpeg(self, file_path: str, force: bool = False) -> JPEGRecoveryResult:
        """Attempt to recover a corrupt JPEG file.

        Args:
            file_path: Path to corrupt JPEG
            force: If True, attempt recovery even if file appears clean

        Returns:
            JPEGRecoveryResult with outcome
        """
        original_path = str(file_path)

        # Check if corrupt (skip if force=True)
        if not force:
            is_corrupt, corruption_type = self.is_corrupt_jpeg(file_path)
            if not is_corrupt:
                logger.debug(f"File is not corrupt, skipping: {file_path}")
                return JPEGRecoveryResult(
                    success=False,
                    original_path=original_path,
                    error="not_corrupt"
                )
        else:
            corruption_type = "forced_recovery"

        logger.info(f"Attempting to recover JPEG: {file_path} (type: {corruption_type or 'unknown'})")

        try:
            # Determine output path
            if self.recovery_dir:
                output_path = self.recovery_dir / Path(file_path).name
            else:
                # Save in same directory with .recovered.jpg suffix
                base = Path(file_path).stem
                parent = Path(file_path).parent
                output_path = parent / f"{base}.recovered.jpg"

            # Attempt recovery with aggressive error handling
            with Image.open(file_path) as img:
                # Force load the entire image to catch hidden corruption
                try:
                    img.load()
                except Exception as e:
                    logger.warning(f"Error during image load, continuing anyway: {e}")

                # Convert to RGB if needed
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                # Try to extract EXIF data
                exif_data = None
                try:
                    exif_data = img.info.get('exif')
                except Exception:
                    logger.debug(f"Could not extract EXIF from {file_path}")

                # Save as clean JPEG
                save_kwargs = {
                    'format': 'JPEG',
                    'quality': self.quality,
                    'optimize': True,
                }

                if exif_data:
                    save_kwargs['exif'] = exif_data

                img.save(output_path, **save_kwargs)

            # Verify the recovered file can actually be rendered (not just verified)
            try:
                with Image.open(output_path) as test:
                    test.load()  # Force full decode
                    test.verify()
            except Exception as e:
                logger.warning(f"Recovered file verification failed: {e}, but file was saved")
                # Don't fail - the file might still be partially usable

            logger.info(f"Successfully recovered: {file_path} -> {output_path}")

            # Optionally remove original
            if not self.preserve_originals:
                # Backup to .bak before removing
                backup_path = f"{file_path}.corrupt.bak"
                shutil.move(file_path, backup_path)
                logger.info(f"Moved corrupt original to: {backup_path}")

            return JPEGRecoveryResult(
                success=True,
                original_path=original_path,
                recovered_path=str(output_path),
                corruption_type=corruption_type,
            )

        except Exception as e:
            logger.error(f"Failed to recover {file_path}: {e}")
            return JPEGRecoveryResult(
                success=False,
                original_path=original_path,
                error=str(e),
                corruption_type=corruption_type,
            )

    def recover_directory(
        self,
        directory: str,
        recursive: bool = True,
        extensions: tuple = ('.jpg', '.jpeg', '.JPG', '.JPEG'),
    ) -> dict:
        """Recover all corrupt JPEGs in a directory.

        Args:
            directory: Directory to scan
            recursive: If True, scan subdirectories
            extensions: File extensions to check

        Returns:
            Dictionary with recovery statistics
        """
        directory = Path(directory)
        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return {'error': 'directory_not_found'}

        logger.info(f"Scanning directory for corrupt JPEGs: {directory}")

        # Find JPEG files
        if recursive:
            files = [f for ext in extensions for f in directory.rglob(f"*{ext}")]
        else:
            files = [f for ext in extensions for f in directory.glob(f"*{ext}")]

        stats = {
            'total_files': len(files),
            'corrupt_found': 0,
            'recovered': 0,
            'failed': 0,
            'not_corrupt': 0,
            'results': [],
        }

        logger.info(f"Found {len(files)} JPEG files to check")

        for file_path in files:
            result = self.recover_jpeg(str(file_path))

            if result.error == "not_corrupt":
                stats['not_corrupt'] += 1
            elif result.success:
                stats['corrupt_found'] += 1
                stats['recovered'] += 1
                stats['results'].append(result)
            else:
                stats['corrupt_found'] += 1
                stats['failed'] += 1
                stats['results'].append(result)

        logger.info(
            f"Recovery complete: {stats['recovered']} recovered, "
            f"{stats['failed']} failed, {stats['not_corrupt']} clean"
        )

        return stats


def recover_jpeg_for_analysis(file_path: str, temp_dir: str | None = None) -> str | None:
    """Quick recovery for a single JPEG before analysis.

    This is a convenience function that attempts to recover a corrupt JPEG
    to a temporary location for immediate analysis without modifying the original.

    Args:
        file_path: Path to potentially corrupt JPEG
        temp_dir: Temporary directory for recovered file

    Returns:
        Path to recovered file if successful, None otherwise
    """
    if temp_dir:
        recovery_dir = temp_dir
    else:
        import tempfile
        recovery_dir = tempfile.gettempdir()

    recovery = JPEGRecovery(
        recovery_dir=recovery_dir,
        preserve_originals=True,
        quality=95,
    )

    result = recovery.recover_jpeg(file_path)

    if result.success and result.recovered_path:
        return result.recovered_path
    return None
