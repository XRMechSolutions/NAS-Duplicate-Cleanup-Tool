"""Metadata extraction for images.

Extracts EXIF fields, GPS, dimensions, and basic camera info into file_metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from duplicleaner.db.database import Database
from duplicleaner.db.models import FileMetadata, FileRecord
from duplicleaner.utils.config import get_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

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

try:
    from dateutil import parser as date_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


@dataclass
class MetadataProgress:
    """Progress tracking for metadata extraction."""
    total_files: int = 0
    processed_files: int = 0
    current_file: str = ""
    phase: str = "initializing"

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class MetadataExtractor:
    """Extracts file metadata for images."""

    def __init__(self, db: Database, enable_location_lookup: Optional[bool] = None) -> None:
        self.db = db
        self.config = get_config()
        self.progress = MetadataProgress()
        self._location_cache: dict[tuple[float, float], str] = {}
        self._geocoder = None

        lookup_enabled = enable_location_lookup
        if lookup_enabled is None:
            lookup_enabled = bool(self.config.ai.metadata_location_lookup)

        if lookup_enabled and HAS_GEOPY:
            try:
                self._geocoder = Nominatim(user_agent="duplicleaner")
            except Exception as exc:
                logger.warning("Failed to initialize geocoder: %s", exc)

    def analyze_file(self, file_record: FileRecord) -> Optional[FileMetadata]:
        """Extract metadata for a single image file and store it."""
        if not file_record.id:
            return None
        if not file_record.is_image:
            return None

        metadata = self._extract_metadata(file_record.path, file_record.id)
        if metadata:
            self.db.add_file_metadata(metadata)
        return metadata

    def analyze_batch(self, file_records: list[FileRecord]) -> int:
        """Extract metadata for a batch of image files."""
        self.progress = MetadataProgress(
            total_files=len(file_records),
            phase="extracting",
        )

        extracted = 0
        for i, file_record in enumerate(file_records):
            self.progress.processed_files = i + 1
            self.progress.current_file = file_record.path
            if self.analyze_file(file_record):
                extracted += 1
        self.progress.phase = "complete"
        return extracted

    def _extract_metadata(self, file_path: str, file_id: int) -> Optional[FileMetadata]:
        """Extract EXIF and basic metadata from an image."""
        exif_data: dict[str, str] = {}
        width = height = None
        exif_date = None
        camera_make = None
        camera_model = None
        orientation = None
        gps_lat = gps_lon = None
        location_name = None

        if HAS_EXIFREAD:
            try:
                with open(file_path, "rb") as f:
                    tags = exifread.process_file(f, details=False)
                if not tags:
                    ext = Path(file_path).suffix.lower() or "no extension"
                    logger.warning("EXIF format not recognized for %s (%s)", file_path, ext)
                for key, value in tags.items():
                    exif_data[key] = str(value)

                exif_date = self._parse_exif_date(
                    str(tags.get("EXIF DateTimeOriginal") or "")
                    or str(tags.get("EXIF DateTimeDigitized") or "")
                    or str(tags.get("Image DateTime") or "")
                )
                camera_make = self._safe_str(tags.get("Image Make"))
                camera_model = self._safe_str(tags.get("Image Model"))
                orientation = self._parse_orientation(tags.get("Image Orientation") or tags.get("EXIF Orientation"))

                gps = self._extract_gps_from_exifread(tags)
                if gps:
                    gps_lat, gps_lon = gps
            except Exception as exc:
                logger.debug("exifread failed for %s: %s", file_path, exc)

        if HAS_PIL:
            try:
                with Image.open(file_path) as img:
                    width, height = img.size
                    exif = img._getexif() if hasattr(img, "_getexif") else None
                    if exif:
                        for tag_id, value in exif.items():
                            tag = TAGS.get(tag_id, tag_id)
                            exif_data.setdefault(str(tag), self._safe_str(value))
                        if exif_date is None:
                            exif_date = self._parse_exif_date(
                                self._safe_str(exif.get(self._tag_id("DateTimeOriginal")))
                                or self._safe_str(exif.get(self._tag_id("DateTimeDigitized")))
                                or self._safe_str(exif.get(self._tag_id("DateTime")))
                            )
                        if camera_make is None:
                            camera_make = self._safe_str(exif.get(self._tag_id("Make")))
                        if camera_model is None:
                            camera_model = self._safe_str(exif.get(self._tag_id("Model")))
                        if orientation is None:
                            orientation = self._parse_orientation(exif.get(self._tag_id("Orientation")))

                        if gps_lat is None or gps_lon is None:
                            gps = self._extract_gps_from_pil(exif)
                            if gps:
                                gps_lat, gps_lon = gps
            except Exception as exc:
                logger.debug("PIL metadata failed for %s: %s", file_path, exc)

        if gps_lat is not None and gps_lon is not None and self._geocoder:
            location_name = self._lookup_location(gps_lat, gps_lon)

        if not any([exif_date, gps_lat, gps_lon, camera_make, camera_model, width, height, orientation, exif_data]):
            return None

        return FileMetadata(
            file_id=file_id,
            exif_date=exif_date,
            gps_lat=gps_lat,
            gps_lon=gps_lon,
            location_name=location_name,
            camera_make=camera_make,
            camera_model=camera_model,
            width=width,
            height=height,
            duration_seconds=None,
            orientation=orientation,
            raw_exif=json.dumps(exif_data) if exif_data else None,
        )

    def _safe_str(self, value: object) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _parse_exif_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        date_str = date_str.strip()
        if not date_str:
            return None
        formats = [
            "%Y:%m:%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y%m%d_%H%M%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        if HAS_DATEUTIL:
            try:
                return date_parser.parse(date_str)
            except Exception:
                return None
        return None

    def _parse_orientation(self, value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(str(value).split()[0])
        except Exception:
            return None

    def _extract_gps_from_exifread(self, tags: dict) -> Optional[tuple[float, float]]:
        try:
            lat = tags.get("GPS GPSLatitude")
            lat_ref = tags.get("GPS GPSLatitudeRef")
            lon = tags.get("GPS GPSLongitude")
            lon_ref = tags.get("GPS GPSLongitudeRef")
            if not (lat and lon and lat_ref and lon_ref):
                return None

            lat_val = self._convert_gps_coord(lat.values)
            lon_val = self._convert_gps_coord(lon.values)

            if str(lat_ref) == "S":
                lat_val = -lat_val
            if str(lon_ref) == "W":
                lon_val = -lon_val
            return (lat_val, lon_val)
        except Exception:
            return None

    def _extract_gps_from_pil(self, exif: dict) -> Optional[tuple[float, float]]:
        try:
            gps_info = exif.get(self._tag_id("GPSInfo"))
            if not gps_info:
                return None
            gps_parsed = {}
            for key, val in gps_info.items():
                gps_tag = GPSTAGS.get(key, key)
                gps_parsed[gps_tag] = val
            lat = gps_parsed.get("GPSLatitude")
            lat_ref = gps_parsed.get("GPSLatitudeRef")
            lon = gps_parsed.get("GPSLongitude")
            lon_ref = gps_parsed.get("GPSLongitudeRef")
            if not (lat and lon and lat_ref and lon_ref):
                return None
            lat_val = self._convert_gps_ratio(lat)
            lon_val = self._convert_gps_ratio(lon)
            if lat_ref == "S":
                lat_val = -lat_val
            if lon_ref == "W":
                lon_val = -lon_val
            return (lat_val, lon_val)
        except Exception:
            return None

    def _convert_gps_coord(self, coord: list) -> float:
        d = float(coord[0].num) / float(coord[0].den)
        m = float(coord[1].num) / float(coord[1].den)
        s = float(coord[2].num) / float(coord[2].den)
        return d + (m / 60.0) + (s / 3600.0)

    def _convert_gps_ratio(self, coord: tuple) -> float:
        def _to_float(value):
            try:
                return float(value[0]) / float(value[1])
            except Exception:
                return float(value)
        d = _to_float(coord[0])
        m = _to_float(coord[1])
        s = _to_float(coord[2])
        return d + (m / 60.0) + (s / 3600.0)

    def _tag_id(self, name: str) -> Optional[int]:
        for tag_id, tag_name in TAGS.items():
            if tag_name == name:
                return tag_id
        return None

    def _lookup_location(self, lat: float, lon: float) -> Optional[str]:
        if not self._geocoder:
            return None
        cache_key = (round(lat, 3), round(lon, 3))
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]
        try:
            location = self._geocoder.reverse(f"{lat}, {lon}", language="en", timeout=5)
            if location and location.raw:
                address = location.raw.get("address", {})
                city = address.get("city") or address.get("town") or address.get("village")
                country = address.get("country")
                state = address.get("state")
                level = self.config.ai.metadata_location_level
                if level == "city":
                    name = city
                elif level == "city_country":
                    name = f"{city}_{country}" if city and country else city or country
                else:
                    parts = [p for p in [city, state, country] if p]
                    name = "_".join(parts)
                if name:
                    self._location_cache[cache_key] = name
                    return name
        except (GeocoderTimedOut, GeocoderServiceError) as exc:
            logger.warning("Geocoding failed: %s", exc)
        except Exception as exc:
            logger.debug("Geocoding error: %s", exc)
        return None
