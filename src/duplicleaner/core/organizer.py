"""Photo Organizer for DupliCleaner.

Transforms unorganized photo dumps into clean, browsable folder structures.
Organizes by date, location, and events based on EXIF metadata.
"""

import contextlib
import json
import mimetypes
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from duplicleaner.ai.objects import ObjectDetector
from duplicleaner.ai.ocr import OCREngine
from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import ActionLogEntry, ActionType, Drive, FileMetadata, FileRecord
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Try to import optional dependencies
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("Pillow not installed. EXIF extraction limited.")

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False

try:
    from geopy.exc import GeocoderServiceError, GeocoderTimedOut
    from geopy.geocoders import Nominatim
    HAS_GEOPY = True
except ImportError:
    HAS_GEOPY = False
    logger.warning("geopy not installed. Location lookup disabled.")

try:
    from dateutil import parser as date_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


class DateFormat(Enum):
    """Folder structure date format options."""

    YYYY_MM = "YYYY/MM"
    YYYY_MM_MONTH = "YYYY/MM-Month"
    YYYY_MM_DD = "YYYY/MM/DD"
    YYYY_FULL_DATE = "YYYY/YYYY-MM-DD"


class ScreenshotHandling(Enum):
    """How to handle screenshots."""

    MIX = "mix"  # Mix with regular photos
    SEPARATE = "separate"  # Separate folder


class BurstHandling(Enum):
    """How to handle burst photos."""

    KEEP_ALL = "keep_all"
    KEEP_BEST = "keep_best"
    SUBFOLDER = "subfolder"
    FLAG = "flag"


class LivePhotoHandling(Enum):
    """How to handle Live Photos."""

    KEEP_TOGETHER = "keep_together"
    VIDEO_SUBFOLDER = "video_subfolder"


class ConflictResolution(Enum):
    """How to handle filename conflicts."""

    ADD_SEQUENCE = "add_sequence"
    ADD_TIMESTAMP = "add_timestamp"
    SKIP = "skip"
    OVERWRITE_IF_IDENTICAL = "overwrite_if_identical"


class UndatedHandling(Enum):
    """How to handle photos without dates."""

    UNDATED_FOLDER = "undated_folder"
    USE_FILE_DATE = "use_file_date"
    SKIP = "skip"


@dataclass
class OrganizeSettings:
    """Settings for photo organization."""

    # Folder structure
    date_format: DateFormat = DateFormat.YYYY_MM_MONTH
    include_location: bool = False
    event_clustering: bool = False
    event_gap_hours: int = 4

    # File naming
    rename_files: bool = True
    rename_pattern: str = "{date}_{seq}"  # Options: {date}, {location}, {time}, {seq}, {original}
    sequence_per_folder: bool = True

    # Special handling
    screenshot_handling: ScreenshotHandling = ScreenshotHandling.SEPARATE
    burst_handling: BurstHandling = BurstHandling.KEEP_ALL
    live_photo_handling: LivePhotoHandling = LivePhotoHandling.KEEP_TOGETHER
    live_photo_cross_directory: bool = False  # Match Live Photos across directories

    # Operations
    move_files: bool = True  # False = copy
    dry_run: bool = False
    conflict_resolution: ConflictResolution = ConflictResolution.ADD_SEQUENCE
    undated_handling: UndatedHandling = UndatedHandling.UNDATED_FOLDER

    # Location settings
    location_level: str = "city"  # city, city_country, full

    # AI Features
    generate_thumbnails: bool = True
    run_object_detection: bool = False
    run_document_classification: bool = False


@dataclass
class OrganizeResult:
    """Result of a single file organization."""

    source_path: str
    dest_path: str
    success: bool
    action: str  # "move", "copy", "skip", "error"
    error: str | None = None
    date_source: str | None = None  # "exif", "file", "undated"
    location: str | None = None
    event_name: str | None = None
    burst_group: int | None = None  # Burst group ID if part of a burst
    is_live_photo: bool = False  # True if this is part of a Live Photo pair
    # AI Fields
    ai_tags: list[str] = field(default_factory=list)
    is_document: bool = False
    thumbnail_path: str | None = None



@dataclass
class OrganizePreview:
    """Preview of organization before executing."""

    total_files: int = 0
    files_to_move: int = 0
    files_to_rename: int = 0
    files_to_skip: int = 0
    folders_to_create: int = 0
    bursts_detected: int = 0  # Number of burst groups found
    live_photos_detected: int = 0  # Number of Live Photo pairs found
    changes: list[OrganizeResult] = field(default_factory=list)
    folders: dict[str, int] = field(default_factory=dict)  # folder -> count
    errors: list[str] = field(default_factory=list)


@dataclass
class OrganizeProgress:
    """Progress tracking for organization."""

    total_files: int = 0
    processed_files: int = 0
    successful: int = 0
    skipped: int = 0
    failed: int = 0
    current_file: str = ""
    state: str = "idle"  # idle, running, paused, completed, cancelled, error


class Organizer:
    """Photo organization engine."""

    # Common screenshot dimensions
    SCREENSHOT_DIMENSIONS = {
        (1920, 1080), (2560, 1440), (3840, 2160),  # Desktop
        (1080, 1920), (1440, 2560), (2160, 3840),  # Portrait desktop
        (1170, 2532), (1284, 2778), (1242, 2688),  # iPhone
        (1080, 2340), (1080, 2400), (1440, 3200),  # Android
    }

    SCREENSHOT_PATTERNS = [
        r"screenshot",
        r"screen.?shot",
        r"screen.?capture",
        r"snip",
    ]

    MONTH_NAMES = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    IMAGE_FILE_TYPES = [
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
        '.webp', '.heic', '.heif', '.raw', '.cr2', '.nef', '.arw'
    ]
    VIDEO_FILE_TYPES = [
        '.mp4', '.mov', '.avi', '.mkv', '.m4v', '.mts'
    ]

    def __init__(
        self,
        db: Database | None = None,
        settings: OrganizeSettings | None = None,
        object_detector: ObjectDetector | None = None,
        ocr_engine: OCREngine | None = None,
    ):
        """Initialize the organizer.

        Args:
            db: Database instance (uses singleton if not provided)
            settings: Organization settings (uses defaults if not provided)
            object_detector: Optional pre-initialized object detector
            ocr_engine: Optional pre-initialized OCR engine
        """
        self.db = db or get_database()
        self.settings = settings or OrganizeSettings()
        self.progress = OrganizeProgress()

        # AI Engines
        self._object_detector = object_detector
        self._ocr_engine = ocr_engine

        # Location cache to avoid repeated lookups
        self._location_cache: dict[tuple[float, float], str] = {}
        self._thumbnail_cache_dir = tempfile.mkdtemp(prefix="duplicleaner_thumbs_")

        # Geocoder instance
        self._geocoder = None
        if HAS_GEOPY:
            self._geocoder = Nominatim(user_agent="duplicleaner")

        # Callbacks
        self._progress_callback: Callable[[OrganizeProgress], None] | None = None
        self._cancel_requested = False

    def _generate_thumbnail(self, image_path: str, size=(128, 128)) -> str | None:
        """Generate a thumbnail for an image and save it to the cache."""
        if not HAS_PIL:
            return None

        try:
            path = Path(image_path)
            thumb_name = f"{path.stem}_{path.stat().st_mtime}.jpg"
            thumb_path = Path(self._thumbnail_cache_dir) / thumb_name

            if thumb_path.exists():
                return str(thumb_path)

            with Image.open(image_path) as img:
                img.thumbnail(size)
                # Ensure image is RGB before saving as JPEG
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')
                img.save(thumb_path, "JPEG")
            return str(thumb_path)
        except Exception as e:
            logger.debug(f"Thumbnail generation failed for {image_path}: {e}")
            return None

    def _extract_video_frame_image(self, video_path: str) -> str | None:
        """Extract a single frame from a video and save to a temp file."""
        try:
            import cv2
        except ImportError:
            logger.debug("opencv-python-headless not installed; skipping video frame extraction")
            return None

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        try:
            ret, frame = cap.read()
            if not ret or frame is None:
                return None
            fd, temp_path = tempfile.mkstemp(prefix="duplicleaner_vid_", suffix=".jpg")
            os.close(fd)
            cv2.imwrite(temp_path, frame)
            return temp_path
        finally:
            cap.release()

    def set_progress_callback(
        self,
        callback: Callable[[OrganizeProgress], None]
    ) -> None:
        """Set callback for progress updates.

        Args:
            callback: Function called with progress updates
        """
        self._progress_callback = callback

    def cancel(self) -> None:
        """Request cancellation of the current operation."""
        self._cancel_requested = True
        logger.info("Organization cancellation requested")

    def _update_progress(self) -> None:
        """Update progress and call callback."""
        if self._progress_callback:
            self._progress_callback(self.progress)

    def extract_date(self, file_path: str) -> tuple[datetime | None, str]:
        """Extract the best date for a file.

        Priority: EXIF DateTimeOriginal > DateTimeDigitized > File dates

        Args:
            file_path: Path to the file

        Returns:
            Tuple of (datetime, source) where source is 'exif', 'file', or 'unknown'
        """
        path = Path(file_path)

        # Try EXIF first
        exif_date = self._extract_exif_date(file_path)
        if exif_date:
            return exif_date, "exif"

        # Fall back to file dates
        try:
            stat = path.stat()
            # Prefer creation time on Windows, modification time otherwise
            if hasattr(stat, 'st_birthtime'):
                file_date = datetime.fromtimestamp(stat.st_birthtime)
            else:
                file_date = datetime.fromtimestamp(stat.st_mtime)
            return file_date, "file"
        except Exception as e:
            logger.debug(f"Could not get file date for {file_path}: {e}")

        return None, "unknown"

    def _extract_exif_date(self, file_path: str) -> datetime | None:
        """Extract date from EXIF data.

        Args:
            file_path: Path to the image

        Returns:
            Datetime or None
        """
        # Try exifread first (more robust)
        if HAS_EXIFREAD:
            try:
                with open(file_path, 'rb') as f:
                    tags = exifread.process_file(f, details=False)
                if not tags:
                    ext = Path(file_path).suffix.lower() or "no extension"
                    logger.warning("EXIF format not recognized for %s (%s)", file_path, ext)

                for tag in ['EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime']:
                    if tag in tags:
                        date_str = str(tags[tag])
                        return self._parse_exif_date(date_str)
            except Exception as e:
                logger.debug(f"exifread failed for {file_path}: {e}")

        # Try PIL/Pillow
        if HAS_PIL:
            try:
                with Image.open(file_path) as img:
                    exif = img._getexif()
                    if exif:
                        for tag_id, value in exif.items():
                            tag = TAGS.get(tag_id, tag_id)
                            if tag in ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']:
                                return self._parse_exif_date(str(value))
            except Exception as e:
                logger.debug(f"PIL EXIF failed for {file_path}: {e}")

        return None

    def _parse_exif_date(self, date_str: str) -> datetime | None:
        """Parse EXIF date string.

        Args:
            date_str: Date string from EXIF (e.g., "2024:01:15 14:30:22")

        Returns:
            Datetime or None
        """
        # Common EXIF format
        formats = [
            "%Y:%m:%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y%m%d_%H%M%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Try dateutil parser as fallback
        if HAS_DATEUTIL:
            try:
                return date_parser.parse(date_str)
            except Exception:
                pass

        return None

    def extract_gps(self, file_path: str) -> tuple[float, float] | None:
        """Extract GPS coordinates from image EXIF.

        Args:
            file_path: Path to the image

        Returns:
            Tuple of (latitude, longitude) or None
        """
        if not HAS_EXIFREAD:
            return None

        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
            if not tags:
                ext = Path(file_path).suffix.lower() or "no extension"
                logger.warning("EXIF format not recognized for %s (%s)", file_path, ext)

            lat = tags.get('GPS GPSLatitude')
            lat_ref = tags.get('GPS GPSLatitudeRef')
            lon = tags.get('GPS GPSLongitude')
            lon_ref = tags.get('GPS GPSLongitudeRef')

            if lat and lon and lat_ref and lon_ref:
                lat_val = self._convert_gps_coord(lat.values)
                lon_val = self._convert_gps_coord(lon.values)

                if str(lat_ref) == 'S':
                    lat_val = -lat_val
                if str(lon_ref) == 'W':
                    lon_val = -lon_val

                return (lat_val, lon_val)

        except Exception as e:
            logger.debug(f"GPS extraction failed for {file_path}: {e}")

        return None

    def _convert_gps_coord(self, coord: list) -> float:
        """Convert GPS coordinate from degrees/minutes/seconds to decimal.

        Args:
            coord: List of [degrees, minutes, seconds]

        Returns:
            Decimal degrees
        """
        d = float(coord[0].num) / float(coord[0].den)
        m = float(coord[1].num) / float(coord[1].den)
        s = float(coord[2].num) / float(coord[2].den)
        return d + (m / 60.0) + (s / 3600.0)

    def get_location_name(
        self,
        lat: float,
        lon: float
    ) -> str | None:
        """Get location name from GPS coordinates.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Location name or None
        """
        if not HAS_GEOPY or not self._geocoder:
            return None

        # Check cache first
        cache_key = (round(lat, 3), round(lon, 3))
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        try:
            location = self._geocoder.reverse(
                f"{lat}, {lon}",
                language="en",
                timeout=5
            )

            if location and location.raw:
                address = location.raw.get('address', {})
                city = address.get('city') or address.get('town') or address.get('village')
                country = address.get('country')
                state = address.get('state')

                if self.settings.location_level == "city":
                    name = city
                elif self.settings.location_level == "city_country":
                    name = f"{city}_{country}" if city and country else city or country
                else:
                    parts = [p for p in [city, state, country] if p]
                    name = "_".join(parts)

                if name:
                    # Clean for filename
                    name = re.sub(r'[^\w\s-]', '', name)
                    name = re.sub(r'\s+', '_', name)
                    self._location_cache[cache_key] = name
                    return name

        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(f"Geocoding failed: {e}")
        except Exception as e:
            logger.debug(f"Geocoding error: {e}")

        return None

    def is_screenshot(self, file_path: str, metadata: FileMetadata | None = None) -> bool:
        """Detect if a file is a screenshot.

        Args:
            file_path: Path to the file
            metadata: Optional pre-loaded metadata

        Returns:
            True if likely a screenshot
        """
        path = Path(file_path)

        # Check filename patterns
        filename_lower = path.stem.lower()
        for pattern in self.SCREENSHOT_PATTERNS:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                return True

        # Check dimensions
        if metadata and metadata.width and metadata.height:
            dims = (metadata.width, metadata.height)
            if dims in self.SCREENSHOT_DIMENSIONS:
                return True

        # Check for lack of camera data with exact screen dimensions
        if HAS_PIL:
            try:
                with Image.open(file_path) as img:
                    if img.size in self.SCREENSHOT_DIMENSIONS:
                        exif = img._getexif()
                        if not exif or 'Make' not in str(exif):
                            return True
            except Exception:
                pass

        # Check CLIP scene classification from database (ML-enhanced detection)
        try:
            file_record = self.db.get_file_by_path_any(file_path)
            if file_record:
                analysis = self.db.get_scene_analysis(file_record.id)
                if analysis and analysis.categories:
                    import json
                    cats = json.loads(analysis.categories) if isinstance(analysis.categories, str) else analysis.categories
                    if isinstance(cats, dict) and cats.get("screenshot", 0) >= 0.6:
                        return True
        except Exception:
            pass

        return False

    def detect_bursts(
        self,
        files: list[tuple[str, datetime]]
    ) -> list[list[str]]:
        """Detect burst photo groups.

        Args:
            files: List of (path, datetime) tuples, sorted by datetime

        Returns:
            List of burst groups (each group is a list of paths)
        """
        bursts = []
        current_burst = []

        for i, (path, dt) in enumerate(files):
            if not current_burst:
                current_burst.append(path)
                continue

            # Check time gap from previous photo
            prev_dt = files[i - 1][1]
            gap = (dt - prev_dt).total_seconds()

            if gap <= 2:  # Within 2 seconds = potential burst
                current_burst.append(path)
            else:
                if len(current_burst) >= 3:  # At least 3 photos = burst
                    bursts.append(current_burst)
                current_burst = [path]

        # Don't forget the last group
        if len(current_burst) >= 3:
            bursts.append(current_burst)

        return bursts

    def _select_best_burst_photo(self, burst_files: list[str]) -> str | None:
        """Select the best photo from a burst group using quality scoring.

        Falls back to file size if quality scores are unavailable.

        Args:
            burst_files: List of file paths in the burst

        Returns:
            Path of the best photo, or None
        """
        if not burst_files:
            return None

        # Try quality scores from database
        best_path = None
        best_score = -1.0

        for path in burst_files:
            file_record = self.db.get_file_by_path_any(path)
            if not file_record:
                continue
            analysis = self.db.get_scene_analysis(file_record.id)
            if analysis and analysis.quality_score is not None:
                if analysis.quality_score > best_score:
                    best_score = analysis.quality_score
                    best_path = path

        if best_path:
            return best_path

        # Fallback: largest file (likely sharpest/least compressed)
        best_path = max(burst_files, key=lambda p: Path(p).stat().st_size if Path(p).exists() else 0)
        return best_path

    def detect_events(
        self,
        files: list[tuple[str, datetime]]
    ) -> list[tuple[datetime, datetime, list[str]]]:
        """Detect event groups based on time gaps.

        Args:
            files: List of (path, datetime) tuples, sorted by datetime

        Returns:
            List of (start_time, end_time, [paths]) tuples
        """
        if not files:
            return []

        gap_threshold = timedelta(hours=self.settings.event_gap_hours)
        events = []
        current_event_start = files[0][1]
        current_event_files = [files[0][0]]

        for i in range(1, len(files)):
            path, dt = files[i]
            prev_dt = files[i - 1][1]
            gap = dt - prev_dt

            if gap > gap_threshold:
                # End current event, start new one
                events.append((
                    current_event_start,
                    prev_dt,
                    current_event_files
                ))
                current_event_start = dt
                current_event_files = [path]
            else:
                current_event_files.append(path)

        # Add final event
        events.append((
            current_event_start,
            files[-1][1],
            current_event_files
        ))

        return events

    def detect_live_photos(
        self,
        files: list[str],
        cross_directory: bool = False,
    ) -> list[tuple[str, str]]:
        """Detect Live Photo pairs (matching image + video files).

        iPhone Live Photos consist of a HEIC/JPG image with a matching MOV video.
        They share the same base filename and are created within milliseconds.
        Samsung/Google Motion Photos embed video data inside the JPEG.

        Args:
            files: List of file paths
            cross_directory: If True, match across directories (slower)

        Returns:
            List of (image_path, video_path) tuples for each Live Photo pair
        """
        image_exts = {'.jpg', '.jpeg', '.heic', '.heif', '.png'}
        video_exts = {'.mov', '.mp4'}

        # --- Phase 1: Apple ContentIdentifier matching ---
        # Maps content_id -> (image_paths, video_paths)
        content_id_images: dict[str, list[str]] = {}
        content_id_videos: dict[str, list[str]] = {}
        content_id_matched: set[str] = set()  # paths already matched by ContentIdentifier

        for path in files:
            ext = Path(path).suffix.lower()
            if ext not in image_exts and ext not in video_exts:
                continue
            cid = self._extract_content_identifier(path)
            if cid:
                if ext in image_exts:
                    content_id_images.setdefault(cid, []).append(path)
                elif ext in video_exts:
                    content_id_videos.setdefault(cid, []).append(path)

        live_photos: list[tuple[str, str]] = []

        # Match by ContentIdentifier (most reliable, works across directories)
        for cid, img_paths in content_id_images.items():
            vid_paths = content_id_videos.get(cid, [])
            if vid_paths:
                for img in img_paths:
                    live_photos.append((img, vid_paths[0]))
                    content_id_matched.add(img)
                    content_id_matched.add(vid_paths[0])

        # --- Phase 2: Filename stem matching (fallback) ---
        # Group files by base name (without extension)
        by_stem: dict[str, list[str]] = {}
        for path in files:
            if path in content_id_matched:
                continue
            p = Path(path)
            stem = p.stem.lower()
            key = stem if cross_directory else f"{p.parent}||{stem}"
            by_stem.setdefault(key, []).append(path)

        for _key, paths in by_stem.items():
            if len(paths) < 2:
                continue

            images = [p for p in paths if Path(p).suffix.lower() in image_exts]
            videos = [p for p in paths if Path(p).suffix.lower() in video_exts]

            if not images or not videos:
                continue

            if cross_directory:
                # Cross-directory: match by stem + timestamp proximity (5 sec)
                for img in images:
                    img_mtime = Path(img).stat().st_mtime if Path(img).exists() else 0
                    best_vid = None
                    best_delta = float('inf')
                    for vid in videos:
                        vid_mtime = Path(vid).stat().st_mtime if Path(vid).exists() else 0
                        delta = abs(img_mtime - vid_mtime)
                        if delta < best_delta:
                            best_delta = delta
                            best_vid = vid
                    if best_vid and best_delta <= 5.0:
                        live_photos.append((img, best_vid))
            else:
                # Same-directory: original behavior
                for img in images:
                    img_path = Path(img)
                    for vid in videos:
                        vid_path = Path(vid)
                        if img_path.parent == vid_path.parent:
                            live_photos.append((img, vid))
                            break

        return live_photos

    def _extract_content_identifier(self, file_path: str) -> str | None:
        """Extract Apple ContentIdentifier from a photo or video.

        Photos store it in XMP metadata (apple-fi:ContentIdentifier).
        Videos store it in QuickTime metadata (com.apple.quicktime.content.identifier).

        Args:
            file_path: Path to the file

        Returns:
            ContentIdentifier UUID string, or None
        """
        ext = Path(file_path).suffix.lower()

        # For images: try XMP metadata
        if ext in {'.jpg', '.jpeg', '.heic', '.heif', '.png'}:
            return self._extract_content_id_from_image(file_path)

        # For videos: try QuickTime atom
        if ext in {'.mov', '.mp4'}:
            return self._extract_content_id_from_video(file_path)

        return None

    def _extract_content_id_from_image(self, file_path: str) -> str | None:
        """Extract ContentIdentifier from image XMP data."""
        try:
            # Read first 64KB where XMP is typically stored
            with open(file_path, 'rb') as f:
                data = f.read(65536)

            # Search for apple-fi:ContentIdentifier in XMP
            # XMP format: <apple-fi:ContentIdentifier>UUID</apple-fi:ContentIdentifier>
            marker = b'ContentIdentifier'
            idx = data.find(marker)
            if idx == -1:
                return None

            # Find the value after the tag
            start = data.find(b'>', idx) + 1
            if start <= 0:
                return None
            end = data.find(b'<', start)
            if end == -1:
                return None

            value = data[start:end].decode('ascii', errors='ignore').strip()
            # ContentIdentifier is typically a UUID (36 chars with dashes)
            if len(value) >= 32 and len(value) <= 40:
                return value

        except Exception as e:
            logger.debug(f"ContentIdentifier extraction failed for {file_path}: {e}")

        return None

    def _extract_content_id_from_video(self, file_path: str) -> str | None:
        """Extract ContentIdentifier from QuickTime metadata."""
        try:
            # Read first 256KB of video for metadata atoms
            with open(file_path, 'rb') as f:
                data = f.read(262144)

            # Search for com.apple.quicktime.content.identifier
            marker = b'com.apple.quicktime.content.identifier'
            idx = data.find(marker)
            if idx == -1:
                # Also check shorter variant
                marker = b'ContentIdentifier'
                idx = data.find(marker)
                if idx == -1:
                    return None

            # The value follows the key in QuickTime metadata
            search_start = idx + len(marker)
            # Look for UUID pattern in the next 100 bytes
            chunk = data[search_start:search_start + 100]
            # UUID pattern: 8-4-4-4-12 hex chars with dashes
            import re
            match = re.search(rb'([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})', chunk)
            if match:
                return match.group(1).decode('ascii')

        except Exception as e:
            logger.debug(f"ContentIdentifier extraction from video failed for {file_path}: {e}")

        return None

    @staticmethod
    def detect_motion_photo(file_path: str) -> int | None:
        """Detect if a JPEG contains an embedded Motion Photo (Samsung/Google).

        Samsung Motion Photos append video data after the JPEG EOI marker (0xFFD9).
        Google Motion Photos use XMP metadata to indicate the video offset.

        Args:
            file_path: Path to the JPEG file

        Returns:
            Byte offset where the video data starts, or None if not a Motion Photo
        """
        ext = Path(file_path).suffix.lower()
        if ext not in {'.jpg', '.jpeg'}:
            return None

        try:
            with open(file_path, 'rb') as f:
                # Check XMP for Motion Photo markers
                header = f.read(65536)

                # Google Motion Photo: look for GCamera:MotionPhoto in XMP
                video_offset = None
                if b'GCamera:MotionPhoto' in header or b'MotionPhoto_Data' in header:
                    # Try to find the video offset from XMP
                    # GCamera:MicroVideoOffset gives bytes from end of file
                    import re
                    match = re.search(rb'MicroVideoOffset["\s>]+(\d+)', header)
                    if match:
                        offset_from_end = int(match.group(1))
                        file_size = Path(file_path).stat().st_size
                        video_offset = file_size - offset_from_end
                    else:
                        # Samsung style: look for MotionPhoto_Data length
                        match = re.search(rb'MotionPhoto_Data["\s>]+(\d+)', header)
                        if match:
                            # offset_from_end for Samsung
                            offset_from_end = int(match.group(1))
                            file_size = Path(file_path).stat().st_size
                            video_offset = file_size - offset_from_end

                if video_offset and video_offset > 0:
                    return video_offset

                # Fallback: scan for video signature after JPEG EOI (0xFFD9)
                f.seek(0)
                data = f.read()

                # Find JPEG EOI marker (search from byte 2 onwards to skip SOI)
                eoi_pos = data.find(b'\xff\xd9', 2)
                if eoi_pos == -1:
                    return None

                # Check if there's significant data after EOI (video)
                remaining = len(data) - (eoi_pos + 2)
                if remaining < 1024:  # Too small to be a video
                    return None

                # Check for common video signatures after EOI
                after_eoi = data[eoi_pos + 2:eoi_pos + 32]
                # ftyp box (MP4/MOV) or Matroska header
                if b'ftyp' in after_eoi or b'mdat' in after_eoi:
                    return eoi_pos + 2

                # Samsung sometimes has padding bytes before the video
                # Scan a bit further for ftyp
                search_region = data[eoi_pos + 2:eoi_pos + 256]
                ftyp_idx = search_region.find(b'ftyp')
                if ftyp_idx >= 4:
                    # ftyp is typically at offset+4 in an MP4 box
                    return eoi_pos + 2 + ftyp_idx - 4

        except Exception as e:
            logger.debug(f"Motion Photo detection failed for {file_path}: {e}")

        return None

    @staticmethod
    def extract_motion_photo_video(file_path: str, output_path: str | None = None) -> str | None:
        """Extract the embedded video from a Motion Photo.

        Args:
            file_path: Path to the Motion Photo JPEG
            output_path: Optional output path. Defaults to same name with .mp4 extension.

        Returns:
            Path to the extracted video file, or None on failure
        """
        video_offset = Organizer.detect_motion_photo(file_path)
        if video_offset is None:
            return None

        if output_path is None:
            output_path = str(Path(file_path).with_suffix('.mp4'))

        try:
            with open(file_path, 'rb') as f:
                f.seek(video_offset)
                video_data = f.read()

            with open(output_path, 'wb') as f:
                f.write(video_data)

            logger.info(f"Extracted Motion Photo video: {output_path} ({len(video_data)} bytes)")
            return output_path

        except Exception as e:
            logger.error(f"Failed to extract Motion Photo video from {file_path}: {e}")
            return None

    def generate_folder_path(
        self,
        date: datetime,
        location: str | None = None,
        event_name: str | None = None
    ) -> str:
        """Generate the destination folder path based on settings.

        Args:
            date: File date
            location: Optional location name
            event_name: Optional event name

        Returns:
            Relative folder path
        """
        year = str(date.year)
        month = f"{date.month:02d}"
        day = f"{date.day:02d}"
        month_name = self.MONTH_NAMES[date.month - 1]

        # Build folder path based on date format
        if self.settings.date_format == DateFormat.YYYY_MM:
            folder = f"{year}/{month}"
        elif self.settings.date_format == DateFormat.YYYY_MM_MONTH:
            folder = f"{year}/{month}-{month_name}"
        elif self.settings.date_format == DateFormat.YYYY_MM_DD:
            folder = f"{year}/{month}/{day}"
        else:  # YYYY_FULL_DATE
            folder = f"{year}/{year}-{month}-{day}"

        # Add event/location subfolder
        if self.settings.event_clustering and event_name:
            folder = f"{folder}/{event_name}"
        elif self.settings.include_location and location:
            folder = f"{folder}/{year}-{month}-{day}_{location}"

        return folder

    def generate_filename(
        self,
        original_path: str,
        date: datetime,
        location: str | None = None,
        sequence: int = 1
    ) -> str:
        """Generate new filename based on settings.

        Args:
            original_path: Original file path
            date: File date
            location: Optional location name
            sequence: Sequence number

        Returns:
            New filename (with extension)
        """
        path = Path(original_path)
        ext = path.suffix.lower()

        if not self.settings.rename_files:
            return path.name

        # Build filename from pattern
        pattern = self.settings.rename_pattern
        filename = pattern

        # Replace placeholders
        date_str = date.strftime("%Y-%m-%d")
        time_str = date.strftime("%H%M")

        filename = filename.replace("{date}", date_str)
        filename = filename.replace("{time}", time_str)
        filename = filename.replace("{seq}", f"{sequence:03d}")
        filename = filename.replace("{original}", path.stem)

        if location:
            filename = filename.replace("{location}", location)
        else:
            # Remove location placeholder and any surrounding underscores
            filename = re.sub(r'_?\{location\}_?', '_', filename)
            filename = re.sub(r'_+', '_', filename)
            filename = filename.strip('_')

        return f"{filename}{ext}"

    def preview(
        self,
        source_dir: str,
        dest_dir: str,
        file_types: list[str] | None = None
    ) -> OrganizePreview:
        """Preview organization without making changes.

        Args:
            source_dir: Source directory to organize
            dest_dir: Destination directory
            file_types: File extensions to include (e.g., ['.jpg', '.png'])

        Returns:
            OrganizePreview with all planned changes
        """
        preview = OrganizePreview()
        source_path = Path(source_dir)
        dest_path = Path(dest_dir)

        # Initialize AI engines if needed and enabled
        if self.settings.run_object_detection and self._object_detector is None:
            self._object_detector = ObjectDetector(self.db)
            self._object_detector.load_model()
        if self.settings.run_document_classification and self._ocr_engine is None:
            self._ocr_engine = OCREngine(self.db)
            self._ocr_engine.load_model()

        if file_types is None:
            file_types = self.IMAGE_FILE_TYPES + self.VIDEO_FILE_TYPES

        # Collect all files with dates
        files_with_dates: list[tuple[str, datetime, str]] = []

        for file_path in source_path.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in file_types:
                continue

            preview.total_files += 1

            date, source = self.extract_date(str(file_path))

            if date is None:
                if self.settings.undated_handling == UndatedHandling.SKIP:
                    preview.files_to_skip += 1
                    continue
                elif self.settings.undated_handling == UndatedHandling.UNDATED_FOLDER:
                    files_with_dates.append((str(file_path), datetime.min, "undated"))
                    continue

            files_with_dates.append((str(file_path), date, source))

        # Sort by date for event detection
        files_with_dates.sort(key=lambda x: x[1])

        # Detect events if enabled
        events = []
        if self.settings.event_clustering:
            dated_files = [(p, d) for p, d, s in files_with_dates if d != datetime.min]
            events = self.detect_events(dated_files)

        # Detect bursts
        burst_map: dict[str, int] = {}  # file_path -> burst_group_id
        burst_best: set[str] = set()  # paths of best photos in each burst
        if self.settings.burst_handling != BurstHandling.KEEP_ALL:
            dated_files = [(p, d) for p, d, s in files_with_dates if d != datetime.min]
            bursts = self.detect_bursts(dated_files)
            preview.bursts_detected = len(bursts)
            for group_id, burst_files in enumerate(bursts, start=1):
                for path in burst_files:
                    burst_map[path] = group_id

                # Quality-based best selection for KEEP_BEST
                if self.settings.burst_handling == BurstHandling.KEEP_BEST:
                    best_path = self._select_best_burst_photo(burst_files)
                    if best_path:
                        burst_best.add(best_path)

        # Detect live photos
        live_photo_videos: set[str] = set()  # video paths that are part of Live Photos
        live_photo_images: set[str] = set()  # image paths that are part of Live Photos
        all_paths = [p for p, d, s in files_with_dates]
        live_photos = self.detect_live_photos(
            all_paths,
            cross_directory=self.settings.live_photo_cross_directory,
        )
        preview.live_photos_detected = len(live_photos)
        for img_path, vid_path in live_photos:
            live_photo_images.add(img_path)
            live_photo_videos.add(vid_path)

        # Process each file
        folder_sequences: dict[str, int] = {}
        folders_to_create: set[str] = set()

        for file_path, date, date_source in files_with_dates:
            # AI analysis
            ai_tags = []
            is_document = False
            thumbnail_path = None

            is_image = Path(file_path).suffix.lower() in self.IMAGE_FILE_TYPES
            is_video = Path(file_path).suffix.lower() in self.VIDEO_FILE_TYPES

            if is_image:
                if self.settings.generate_thumbnails:
                    thumbnail_path = self._generate_thumbnail(file_path)

                # First, try to classify as a document
                if self.settings.run_document_classification and self._ocr_engine:
                    ocr_result = self._ocr_engine.extract_text(file_path)
                    logger.info(f"File: {file_path}, OCR Result: {ocr_result}, Full Text Length: {len(ocr_result.full_text) if ocr_result else 'N/A'}")
                    if ocr_result and len(ocr_result.full_text) > 100:  # Heuristic for being a document
                        is_document = True
                        logger.debug(f"File: {file_path} classified as document. is_document: {is_document}")

                # Auto-OCR for screenshots (even if document classification is off)
                if not is_document and self.is_screenshot(file_path):
                    if self._ocr_engine is None:
                        try:
                            self._ocr_engine = OCREngine(self.db)
                            self._ocr_engine.load_model()
                        except Exception:
                            pass
                    if self._ocr_engine:
                        try:
                            file_record = self.db.get_file_by_path_any(file_path)
                            if file_record:
                                self._ocr_engine.analyze_file(file_record)
                        except Exception as e:
                            logger.debug(f"Screenshot OCR failed for {file_path}: {e}")

                # If it's not a document (or document classification was not enabled), then run object detection
                if not is_document and self.settings.run_object_detection and self._object_detector:
                    obj_result = self._object_detector.detect_objects(file_path)
                    if obj_result:
                        ai_tags = obj_result.unique_labels
                        logger.debug(f"File: {file_path} object detection tags: {ai_tags}")

            if is_video:
                frame_path = None
                try:
                    frame_path = self._extract_video_frame_image(file_path)
                    if frame_path:
                        if self.settings.generate_thumbnails:
                            thumbnail_path = self._generate_thumbnail(frame_path)
                        if self.settings.run_object_detection and self._object_detector:
                            obj_result = self._object_detector.detect_objects(frame_path)
                            if obj_result:
                                ai_tags = obj_result.unique_labels
                finally:
                    if (
                        frame_path
                        and os.path.exists(frame_path)
                        and Path(frame_path).name.startswith("duplicleaner_vid_")
                    ):
                        with contextlib.suppress(OSError):
                            os.remove(frame_path)

            # Handle undated files
            if date == datetime.min:
                folder = "Undated"
                location = None
                event_name = None
            else:
                # Get location if enabled
                location = None
                if self.settings.include_location:
                    gps = self.extract_gps(file_path)
                    if gps:
                        location = self.get_location_name(gps[0], gps[1])

                # Find event name if clustering
                event_name = None
                if self.settings.event_clustering and events:
                    for start, end, paths in events:
                        if file_path in paths:
                            event_date = start.strftime("%Y-%m-%d")
                            event_idx = events.index((start, end, paths)) + 1
                            if location:
                                event_name = f"{event_date}_{location}"
                            else:
                                event_name = f"{event_date}_Event{event_idx}"
                            break

                folder = self.generate_folder_path(date, location, event_name)

            # Check for screenshots
            if self.settings.screenshot_handling == ScreenshotHandling.SEPARATE and self.is_screenshot(file_path):
                folder = "Screenshots/" + folder

            # Handle burst photos
            burst_group = burst_map.get(file_path)
            if burst_group is not None:
                if self.settings.burst_handling == BurstHandling.KEEP_BEST:
                    if file_path not in burst_best:
                        # Skip non-best burst photos
                        preview.files_skipped = getattr(preview, 'files_skipped', 0) + 1
                        continue
                elif self.settings.burst_handling == BurstHandling.SUBFOLDER:
                    folder = f"{folder}/Burst_{burst_group:03d}"

            # Handle Live Photo videos
            is_live_photo = file_path in live_photo_videos or file_path in live_photo_images
            if file_path in live_photo_videos and self.settings.live_photo_handling == LivePhotoHandling.VIDEO_SUBFOLDER:
                folder = f"{folder}/LivePhoto_Videos"

            # Generate sequence number
            if folder not in folder_sequences:
                folder_sequences[folder] = 0
            folder_sequences[folder] += 1
            seq = folder_sequences[folder]

            # Generate filename
            if date != datetime.min:
                new_filename = self.generate_filename(file_path, date, location, seq)
            else:
                new_filename = Path(file_path).name

            # Build full destination path
            full_dest = dest_path / folder / new_filename

            folders_to_create.add(folder)
            preview.files_to_move += 1
            preview.folders[folder] = preview.folders.get(folder, 0) + 1

            if new_filename != Path(file_path).name:
                preview.files_to_rename += 1

            result = OrganizeResult(
                source_path=file_path,
                dest_path=str(full_dest),
                success=True,
                action="move" if self.settings.move_files else "copy",
                date_source=date_source,
                location=location,
                event_name=event_name,
                burst_group=burst_group,
                is_live_photo=is_live_photo,
                ai_tags=ai_tags,
                is_document=is_document,
                thumbnail_path=thumbnail_path,
            )
            preview.changes.append(result)

        preview.folders_to_create = len(folders_to_create)
        return preview

    def execute(
        self,
        source_dir: str,
        dest_dir: str,
        file_types: list[str] | None = None,
        preview: OrganizePreview | None = None
    ) -> list[OrganizeResult]:
        """Execute the organization.

        Args:
            source_dir: Source directory to organize
            dest_dir: Destination directory
            file_types: File extensions to include
            preview: Optional pre-computed preview

        Returns:
            List of OrganizeResult for each file
        """
        self._cancel_requested = False
        self.progress = OrganizeProgress(state="running")

        # Generate preview if not provided
        if preview is None:
            preview = self.preview(source_dir, dest_dir, file_types)

        self.progress.total_files = len(preview.changes)
        self._update_progress()

        results = []
        Path(dest_dir)
        drives = self.db.get_all_drives()

        for i, change in enumerate(preview.changes):
            if self._cancel_requested:
                self.progress.state = "cancelled"
                self._update_progress()
                logger.info("Organization cancelled by user")
                break

            self.progress.processed_files = i + 1
            self.progress.current_file = change.source_path
            self._update_progress()

            # Skip in dry run mode
            if self.settings.dry_run:
                result = OrganizeResult(
                    source_path=change.source_path,
                    dest_path=change.dest_path,
                    success=True,
                    action="dry_run",
                    date_source=change.date_source,
                    location=change.location,
                    event_name=change.event_name,
                    burst_group=change.burst_group,
                    is_live_photo=change.is_live_photo,
                    ai_tags=change.ai_tags,
                    is_document=change.is_document,
                    thumbnail_path=change.thumbnail_path,
                )
                results.append(result)
                self.progress.successful += 1
                continue

            try:
                # Create destination directory
                dest_file = Path(change.dest_path)
                dest_file.parent.mkdir(parents=True, exist_ok=True)

                # Handle conflicts
                if dest_file.exists():
                    if self.settings.conflict_resolution == ConflictResolution.SKIP:
                        result = OrganizeResult(
                            source_path=change.source_path,
                            dest_path=change.dest_path,
                            success=False,
                            action="skip",
                            error="Destination exists"
                        )
                        results.append(result)
                        self.progress.skipped += 1
                        continue
                    elif self.settings.conflict_resolution == ConflictResolution.ADD_SEQUENCE:
                        # Find available sequence number
                        seq = 2
                        stem = dest_file.stem
                        suffix = dest_file.suffix
                        while dest_file.exists():
                            dest_file = dest_file.parent / f"{stem}_{seq:03d}{suffix}"
                            seq += 1

                # Move or copy file
                if self.settings.move_files:
                    shutil.move(change.source_path, str(dest_file))
                    action = "move"
                else:
                    shutil.copy2(change.source_path, str(dest_file))
                    action = "copy"

                # After successful move/copy, save AI data to the database
                new_file_record = self.db.get_file_by_path_any(str(dest_file))
                if not new_file_record:
                    drive_id = self._infer_drive_id_for_path(str(dest_file), drives)
                    if drive_id:
                        stat_info = dest_file.stat()
                        mime_type, _ = mimetypes.guess_type(dest_file.name)
                        record = FileRecord(
                            drive_id=drive_id,
                            path=str(dest_file),
                            filename=dest_file.name,
                            size=stat_info.st_size,
                            created=datetime.fromtimestamp(stat_info.st_ctime),
                            modified=datetime.fromtimestamp(stat_info.st_mtime),
                            file_type=dest_file.suffix.lower() or None,
                            mime_type=mime_type,
                            scan_date=datetime.now(),
                        )
                        file_id = self.db.add_file(record)
                        new_file_record = self.db.get_file(file_id)
                if new_file_record and new_file_record.id:
                    file_id = new_file_record.id
                    # Save scene analysis (tags)
                    if change.ai_tags:
                        from duplicleaner.db.models import SceneAnalysis
                        scene_analysis = SceneAnalysis(
                            file_id=file_id,
                            objects=json.dumps(change.ai_tags),
                            analyzed_at=datetime.now()
                        )
                        self.db.add_scene_analysis(scene_analysis)

                    # Save OCR result (document classification)
                    if change.is_document:
                        from duplicleaner.db.models import OCRResult
                        ocr_result = OCRResult(
                            file_id=file_id,
                            extracted_text="",  # We only have the flag for now
                            created_at=datetime.now()
                        )
                        self.db.add_ocr_result(ocr_result)

                # Log action
                self.db.log_action(ActionLogEntry(
                    action_type=ActionType.MOVE if self.settings.move_files else ActionType.COPY,
                    source_path=change.source_path,
                    dest_path=str(dest_file),
                    metadata=json.dumps({
                        "date_source": change.date_source,
                        "location": change.location,
                        "event": change.event_name,
                        "burst_group": change.burst_group,
                        "is_live_photo": change.is_live_photo,
                        "ai_tags": change.ai_tags,
                        "is_document": change.is_document,
                    })
                ))

                result = OrganizeResult(
                    source_path=change.source_path,
                    dest_path=str(dest_file),
                    success=True,
                    action=action,
                    date_source=change.date_source,
                    location=change.location,
                    event_name=change.event_name,
                    burst_group=change.burst_group,
                    is_live_photo=change.is_live_photo,
                    ai_tags=change.ai_tags,
                    is_document=change.is_document,
                    thumbnail_path=change.thumbnail_path,
                )
                results.append(result)
                self.progress.successful += 1

            except Exception as e:
                logger.error(f"Failed to organize {change.source_path}: {e}")
                result = OrganizeResult(
                    source_path=change.source_path,
                    dest_path=change.dest_path,
                    success=False,
                    action="error",
                    error=str(e),
                    ai_tags=change.ai_tags,
                    is_document=change.is_document,
                    thumbnail_path=change.thumbnail_path,
                )
                results.append(result)
                self.progress.failed += 1

        if not self._cancel_requested:
            self.progress.state = "completed"
        self._update_progress()

        logger.info(
            f"Organization complete: {self.progress.successful} successful, "
            f"{self.progress.failed} failed, {self.progress.skipped} skipped"
        )

        return results

    @staticmethod
    def _infer_drive_id_for_path(path: str, drives: list[Drive]) -> str | None:
        """Infer drive ID by longest matching drive path prefix."""
        if not drives:
            return None
        normalized = os.path.normcase(os.path.normpath(path))
        best_id = None
        best_len = -1
        for drive in drives:
            drive_path = os.path.normcase(os.path.normpath(drive.path))
            if normalized.startswith(drive_path) and len(drive_path) > best_len:
                best_id = drive.id
                best_len = len(drive_path)
        return best_id


def get_exif_date(file_path: str) -> datetime | None:
    """Convenience function to extract EXIF date from a file.

    Args:
        file_path: Path to the image

    Returns:
        Datetime or None
    """
    organizer = Organizer()
    date, _ = organizer.extract_date(file_path)
    return date
