"""Photo Organizer for DupliCleaner.

Transforms unorganized photo dumps into clean, browsable folder structures.
Organizes by date, location, and events based on EXIF metadata.
"""

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import FileRecord, FileMetadata, ActionLogEntry, ActionType
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Try to import optional dependencies
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
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
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
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
    SEPARATE_BY_APP = "separate_by_app"  # Group by source app


class BurstHandling(Enum):
    """How to handle burst photos."""

    KEEP_ALL = "keep_all"
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

    # Operations
    move_files: bool = True  # False = copy
    dry_run: bool = False
    conflict_resolution: ConflictResolution = ConflictResolution.ADD_SEQUENCE
    undated_handling: UndatedHandling = UndatedHandling.UNDATED_FOLDER

    # Location settings
    location_level: str = "city"  # city, city_country, full


@dataclass
class OrganizeResult:
    """Result of a single file organization."""

    source_path: str
    dest_path: str
    success: bool
    action: str  # "move", "copy", "skip", "error"
    error: Optional[str] = None
    date_source: Optional[str] = None  # "exif", "file", "undated"
    location: Optional[str] = None
    event_name: Optional[str] = None


@dataclass
class OrganizePreview:
    """Preview of organization before executing."""

    total_files: int = 0
    files_to_move: int = 0
    files_to_rename: int = 0
    files_to_skip: int = 0
    folders_to_create: int = 0
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

    def __init__(
        self,
        db: Optional[Database] = None,
        settings: Optional[OrganizeSettings] = None
    ):
        """Initialize the organizer.

        Args:
            db: Database instance (uses singleton if not provided)
            settings: Organization settings (uses defaults if not provided)
        """
        self.db = db or get_database()
        self.settings = settings or OrganizeSettings()
        self.progress = OrganizeProgress()

        # Location cache to avoid repeated lookups
        self._location_cache: dict[tuple[float, float], str] = {}

        # Geocoder instance
        self._geocoder = None
        if HAS_GEOPY:
            self._geocoder = Nominatim(user_agent="duplicleaner")

        # Callbacks
        self._progress_callback: Optional[Callable[[OrganizeProgress], None]] = None
        self._cancel_requested = False

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

    def extract_date(self, file_path: str) -> tuple[Optional[datetime], str]:
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

    def _extract_exif_date(self, file_path: str) -> Optional[datetime]:
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

    def _parse_exif_date(self, date_str: str) -> Optional[datetime]:
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

    def extract_gps(self, file_path: str) -> Optional[tuple[float, float]]:
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
    ) -> Optional[str]:
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

    def is_screenshot(self, file_path: str, metadata: Optional[FileMetadata] = None) -> bool:
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

    def generate_folder_path(
        self,
        date: datetime,
        location: Optional[str] = None,
        event_name: Optional[str] = None
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
        location: Optional[str] = None,
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
        file_types: Optional[list[str]] = None
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

        if file_types is None:
            file_types = [
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
                '.webp', '.heic', '.heif', '.raw', '.cr2', '.nef', '.arw',
                '.mp4', '.mov', '.avi', '.mkv', '.m4v', '.mts'
            ]

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

        # Process each file
        folder_sequences: dict[str, int] = {}
        folders_to_create: set[str] = set()

        for file_path, date, date_source in files_with_dates:
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
            if self.settings.screenshot_handling == ScreenshotHandling.SEPARATE:
                if self.is_screenshot(file_path):
                    folder = "Screenshots/" + folder

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
                event_name=event_name
            )
            preview.changes.append(result)

        preview.folders_to_create = len(folders_to_create)
        return preview

    def execute(
        self,
        source_dir: str,
        dest_dir: str,
        file_types: Optional[list[str]] = None,
        preview: Optional[OrganizePreview] = None
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
        dest_path = Path(dest_dir)

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
                    event_name=change.event_name
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

                # Log action
                self.db.log_action(ActionLogEntry(
                    action_type=ActionType.MOVE if self.settings.move_files else ActionType.COPY,
                    source_path=change.source_path,
                    dest_path=str(dest_file),
                    metadata=json.dumps({
                        "date_source": change.date_source,
                        "location": change.location,
                        "event": change.event_name
                    })
                ))

                result = OrganizeResult(
                    source_path=change.source_path,
                    dest_path=str(dest_file),
                    success=True,
                    action=action,
                    date_source=change.date_source,
                    location=change.location,
                    event_name=change.event_name
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
                    error=str(e)
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


def get_exif_date(file_path: str) -> Optional[datetime]:
    """Convenience function to extract EXIF date from a file.

    Args:
        file_path: Path to the image

    Returns:
        Datetime or None
    """
    organizer = Organizer()
    date, _ = organizer.extract_date(file_path)
    return date
